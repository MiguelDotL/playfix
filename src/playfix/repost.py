"""Post the fixed version of a message back to its channel.

Each guild picks one of two strategies:

* ``webhook`` (default) — repost the message through a channel webhook using the
  author's name and avatar, then delete the original, so the fix looks like it came
  from them. Requires *Manage Webhooks* and *Manage Messages*.
* ``reply`` — leave the original in place, suppress its broken preview, and reply
  with the fixed links. Non-destructive, and used automatically as a fallback when
  the bot lacks the permissions webhook mode needs.
"""

from __future__ import annotations

import contextlib
import logging

import discord

from .config import Settings
from .db import GuildConfig
from .rewrite import RewriteResult

log = logging.getLogger(__name__)

# Our webhooks are named this so we can recognise and reuse them after a restart
# instead of piling up a new one each time.
WEBHOOK_NAME = "PlayFix"

# Channel types that can own a webhook.
WEBHOOK_CHANNELS = (discord.TextChannel, discord.VoiceChannel, discord.Thread)

# A repost must never ping anyone — the author's display name or the pasted text
# could otherwise smuggle an @everyone/@role through the webhook.
_NO_MENTIONS = discord.AllowedMentions.none()


class Reposter:
    """Reposts messages with their links fixed, per the guild's chosen strategy."""

    def __init__(self, bot: discord.Client, settings: Settings) -> None:
        self._bot = bot
        self._settings = settings
        self._webhooks: dict[int, discord.Webhook] = {}  # channel id -> our webhook

    async def handle(
        self, message: discord.Message, result: RewriteResult, cfg: GuildConfig
    ) -> None:
        """Repost ``message`` with its links fixed, honouring the guild's settings."""
        assert message.guild is not None  # on_message only forwards guild messages
        perms = message.channel.permissions_for(message.guild.me)

        if self._webhook_allowed(message, cfg, result, perms) and await self._repost_as_author(
            message, result.text
        ):
            if cfg.delete_original:
                await self._delete(message)
            return

        await self._reply_with_fix(message, result, perms)

    def _webhook_allowed(
        self,
        message: discord.Message,
        cfg: GuildConfig,
        result: RewriteResult,
        perms: discord.Permissions,
    ) -> bool:
        return (
            cfg.mode == "webhook"
            and isinstance(message.channel, WEBHOOK_CHANNELS)
            and perms.manage_webhooks
            and perms.manage_messages
            and len(result.text) <= self._settings.max_content_length
        )

    async def _repost_as_author(self, message: discord.Message, content: str) -> bool:
        """Send ``content`` as the author via webhook. Returns whether it worked."""
        channel = message.channel
        thread = channel if isinstance(channel, discord.Thread) else None
        host = channel.parent if thread else channel
        if host is None:  # a thread whose parent we can't see — fall back to a reply
            return False

        try:
            webhook = await self._webhook_for(host)
            await webhook.send(
                content=content or None,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                files=await self._copy_attachments(message),
                allowed_mentions=_NO_MENTIONS,
                thread=thread or discord.utils.MISSING,
            )
            return True
        except (discord.Forbidden, discord.HTTPException):
            log.warning("webhook repost failed in channel %s; replying instead", channel.id)
            return False

    async def _webhook_for(self, channel: discord.abc.GuildChannel) -> discord.Webhook:
        """Return our webhook for ``channel``, reusing or creating it as needed."""
        cached = self._webhooks.get(channel.id)
        if cached is not None:
            return cached
        for webhook in await channel.webhooks():
            if webhook.name == WEBHOOK_NAME and webhook.user == self._bot.user:
                self._webhooks[channel.id] = webhook
                return webhook
        webhook = await channel.create_webhook(name=WEBHOOK_NAME, reason="PlayFix link fix")
        self._webhooks[channel.id] = webhook
        return webhook

    async def _copy_attachments(self, message: discord.Message) -> list[discord.File]:
        """Re-download the author's attachments so the repost keeps them (best effort)."""
        size_limit = self._settings.max_attachment_mb * 1024 * 1024
        files: list[discord.File] = []
        for attachment in message.attachments:
            if attachment.size > size_limit:
                continue
            with contextlib.suppress(discord.HTTPException):
                files.append(await attachment.to_file())
        return files

    async def _reply_with_fix(
        self, message: discord.Message, result: RewriteResult, perms: discord.Permissions
    ) -> None:
        if perms.manage_messages:
            with contextlib.suppress(discord.HTTPException):
                await message.edit(suppress=True)  # hide the broken original preview
        fixed_links = "\n".join(fixed for _, fixed in result.rewrites)
        with contextlib.suppress(discord.HTTPException):
            await message.reply(fixed_links, mention_author=False, allowed_mentions=_NO_MENTIONS)

    @staticmethod
    async def _delete(message: discord.Message) -> None:
        with contextlib.suppress(discord.HTTPException):
            await message.delete()
