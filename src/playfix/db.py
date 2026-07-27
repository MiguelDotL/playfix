"""Per-guild settings, stored in SQLite (no external database server).

Reads are served from an in-memory cache and writes go straight through to disk.
Defaults come from :class:`~playfix.config.Settings`, so a brand-new guild works
with no setup at all.
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
    """The effective PlayFix settings for one guild."""

    guild_id: int
    enabled: bool
    mode: Mode
    delete_original: bool
    disabled_channels: frozenset[int] = field(default_factory=frozenset)


class Database:
    """SQLite-backed store for per-guild settings, with a write-through read cache."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._path = settings.db_path
        self._conn: aiosqlite.Connection | None = None
        self._cache: dict[int, GuildConfig] = {}

    async def init(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.init() must be called before use")
        return self._conn

    # --- reads ---------------------------------------------------------------

    async def get(self, guild_id: int) -> GuildConfig:
        if guild_id not in self._cache:
            self._cache[guild_id] = await self._load(guild_id)
        return self._cache[guild_id]

    async def _load(self, guild_id: int) -> GuildConfig:
        async with self._db.execute(
            "SELECT enabled, mode, delete_original FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
        disabled = await self._disabled_channels(guild_id)
        if row is None:
            return replace(self._defaults(guild_id), disabled_channels=disabled)
        enabled, mode, delete_original = row
        return GuildConfig(
            guild_id=guild_id,
            enabled=bool(enabled),
            mode=mode,
            delete_original=bool(delete_original),
            disabled_channels=disabled,
        )

    def _defaults(self, guild_id: int) -> GuildConfig:
        return GuildConfig(
            guild_id=guild_id,
            enabled=True,
            mode=self._settings.default_mode,
            delete_original=self._settings.default_delete_original,
        )

    async def _disabled_channels(self, guild_id: int) -> frozenset[int]:
        async with self._db.execute(
            "SELECT channel_id FROM disabled_channels WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            return frozenset(channel_id for (channel_id,) in await cursor.fetchall())

    # --- writes --------------------------------------------------------------

    async def set_enabled(self, guild_id: int, enabled: bool) -> GuildConfig:
        return await self._update(guild_id, enabled=enabled)

    async def set_mode(self, guild_id: int, mode: Mode) -> GuildConfig:
        return await self._update(guild_id, mode=mode)

    async def set_delete_original(self, guild_id: int, delete_original: bool) -> GuildConfig:
        return await self._update(guild_id, delete_original=delete_original)

    async def _update(self, guild_id: int, **changes: object) -> GuildConfig:
        cfg = replace(await self.get(guild_id), **changes)
        await self._db.execute(
            "INSERT INTO guild_settings (guild_id, enabled, mode, delete_original) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "enabled = excluded.enabled, mode = excluded.mode, "
            "delete_original = excluded.delete_original",
            (cfg.guild_id, int(cfg.enabled), cfg.mode, int(cfg.delete_original)),
        )
        await self._db.commit()
        self._cache[guild_id] = cfg
        return cfg

    async def set_channel_enabled(
        self, guild_id: int, channel_id: int, enabled: bool
    ) -> GuildConfig:
        if enabled:
            await self._db.execute(
                "DELETE FROM disabled_channels WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
        else:
            await self._db.execute(
                "INSERT OR IGNORE INTO disabled_channels (guild_id, channel_id) VALUES (?, ?)",
                (guild_id, channel_id),
            )
        await self._db.commit()
        self._cache.pop(guild_id, None)  # invalidate so the next read reflects the change
        return await self.get(guild_id)
