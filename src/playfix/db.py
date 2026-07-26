"""Per-guild settings, persisted in SQLite (no external DB server).

Reads are served from an in-memory cache; writes are write-through. Defaults come
from :class:`~playfix.config.Settings`, so a brand-new guild works with zero setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

import aiosqlite

from .config import Mode, Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id        INTEGER PRIMARY KEY,
    enabled         INTEGER NOT NULL,
    mode            TEXT    NOT NULL,
    delete_original INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS disabled_channels (
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
"""


@dataclass(frozen=True, slots=True)
class GuildConfig:
    """Effective settings for one guild."""

    guild_id: int
    enabled: bool
    mode: Mode
    delete_original: bool
    disabled_channels: frozenset[int] = field(default_factory=frozenset)


class Database:
    """Async SQLite-backed store for per-guild settings, with a read cache."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._path = settings.db_path
        self._conn: aiosqlite.Connection | None = None
        self._cache: dict[int, GuildConfig] = {}

    async def init(self) -> None:
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _default(self, guild_id: int) -> GuildConfig:
        return GuildConfig(
            guild_id=guild_id,
            enabled=True,
            mode=self._settings.default_mode,
            delete_original=self._settings.default_delete_original,
        )

    async def get(self, guild_id: int) -> GuildConfig:
        cached = self._cache.get(guild_id)
        if cached is not None:
            return cached
        assert self._conn is not None
        async with self._conn.execute(
            "SELECT enabled, mode, delete_original FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            cfg = self._default(guild_id)
        else:
            channels = await self._load_disabled_channels(guild_id)
            cfg = GuildConfig(
                guild_id=guild_id,
                enabled=bool(row[0]),
                mode=row[1],
                delete_original=bool(row[2]),
                disabled_channels=channels,
            )
        self._cache[guild_id] = cfg
        return cfg

    async def _load_disabled_channels(self, guild_id: int) -> frozenset[int]:
        assert self._conn is not None
        async with self._conn.execute(
            "SELECT channel_id FROM disabled_channels WHERE guild_id = ?", (guild_id,)
        ) as cur:
            return frozenset(r[0] for r in await cur.fetchall())

    async def _upsert(self, cfg: GuildConfig) -> None:
        assert self._conn is not None
        await self._conn.execute(
            "INSERT INTO guild_settings (guild_id, enabled, mode, delete_original) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
            "enabled = excluded.enabled, mode = excluded.mode, "
            "delete_original = excluded.delete_original",
            (cfg.guild_id, int(cfg.enabled), cfg.mode, int(cfg.delete_original)),
        )
        await self._conn.commit()
        self._cache[cfg.guild_id] = cfg

    async def set_enabled(self, guild_id: int, enabled: bool) -> GuildConfig:
        cfg = replace(await self.get(guild_id), enabled=enabled)
        await self._upsert(cfg)
        return cfg

    async def set_mode(self, guild_id: int, mode: Mode) -> GuildConfig:
        cfg = replace(await self.get(guild_id), mode=mode)
        await self._upsert(cfg)
        return cfg

    async def set_delete_original(self, guild_id: int, value: bool) -> GuildConfig:
        cfg = replace(await self.get(guild_id), delete_original=value)
        await self._upsert(cfg)
        return cfg

    async def set_channel_enabled(
        self, guild_id: int, channel_id: int, enabled: bool
    ) -> GuildConfig:
        assert self._conn is not None
        if enabled:
            await self._conn.execute(
                "DELETE FROM disabled_channels WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
        else:
            await self._conn.execute(
                "INSERT OR IGNORE INTO disabled_channels (guild_id, channel_id) VALUES (?, ?)",
                (guild_id, channel_id),
            )
        await self._conn.commit()
        # Ensure a base row exists so the guild persists, then refresh cache.
        base = await self.get(guild_id)
        await self._upsert(base)
        self._cache.pop(guild_id, None)
        return await self.get(guild_id)
