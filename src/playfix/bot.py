"""The Discord client: wires message events to the rewrite + repost pipeline."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .commands import PlayFixCommands
from .config import Settings
from .db import Database
from .repost import handle
from .rewrite import rewrite_text

log = logging.getLogger(__name__)


class PlayFix(commands.Bot):
    """PlayFix bot: watches for social links and makes them play."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.settings = settings
        self.db = Database(settings)
        # Per-channel webhook cache used by repost._get_webhook.
        self._playfix_webhooks: dict[int, discord.Webhook] = {}

    async def setup_hook(self) -> None:
        await self.db.init()
        self.tree.add_command(PlayFixCommands(self))
        await self.tree.sync()
        log.info("slash commands synced")

    async def on_ready(self) -> None:
        log.info("logged in as %s across %d guild(s)", self.user, len(self.guilds))

    async def on_message(self, message: discord.Message) -> None:
        # Ignore our own reposts, other bots/webhooks (no loops) and DMs.
        if message.author.bot or message.webhook_id is not None or message.guild is None:
            return
        if not message.content:
            return
        try:
            cfg = await self.db.get(message.guild.id)
            if not cfg.enabled or message.channel.id in cfg.disabled_channels:
                return
            result = rewrite_text(message.content)
            if not result.changed:
                return
            await handle(
                self,
                message,
                result,
                cfg,
                max_attachment_bytes=self.settings.max_attachment_mb * 1024 * 1024,
                max_content_length=self.settings.max_content_length,
            )
        except Exception:  # never let one bad message kill the handler
            log.exception("failed handling message %s", message.id)

    async def close(self) -> None:
        await self.db.close()
        await super().close()
