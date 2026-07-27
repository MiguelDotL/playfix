"""The Discord client — wires message events into the rewrite → repost pipeline."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .commands import PlayFixCommands
from .config import Settings
from .db import Database
from .repost import Reposter
from .rewrite import rewrite_text

log = logging.getLogger(__name__)


class PlayFix(commands.Bot):
    """Watches for social-media links and reposts them so they play."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)

        self.settings = settings
        self.db = Database(settings)
        self.reposter = Reposter(self, settings)

    async def setup_hook(self) -> None:
        await self.db.init()
        self.tree.add_command(PlayFixCommands(self))
        await self.tree.sync()
        log.info("slash commands synced")

    async def on_ready(self) -> None:
        log.info("logged in as %s across %d guild(s)", self.user, len(self.guilds))

    async def on_message(self, message: discord.Message) -> None:
        if not self._should_handle(message):
            return
        try:
            cfg = await self.db.get(message.guild.id)  # guild is set (see _should_handle)
            if not cfg.enabled or message.channel.id in cfg.disabled_channels:
                return
            result = rewrite_text(message.content)
            if result.changed:
                await self.reposter.handle(message, result, cfg)
        except Exception:  # one bad message must never take the bot down
            log.exception("failed to handle message %s", message.id)

    @staticmethod
    def _should_handle(message: discord.Message) -> bool:
        # Skip our own reposts, other bots/webhooks (avoids loops), DMs, and empties.
        return (
            message.guild is not None
            and not message.author.bot
            and message.webhook_id is None
            and bool(message.content)
        )

    async def close(self) -> None:
        await self.db.close()
        await super().close()
