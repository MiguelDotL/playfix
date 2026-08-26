"""Post the fixed version of a message back to its channel.

Each guild picks one of two strategies:

* ``webhook`` (default) — repost the message through a channel webhook using the
  author's name and avatar, then delete the original, so the fix looks like it came
  from them. Requires *Manage Webhooks* and *Manage Messages*.
* ``reply`` — leave the original in place, suppress its broken preview, and reply
  with the fixed links. Non-destructive, and used automatically as a fallback when
  the bot lacks the permissions webhook mode needs.

Posting the fixed link is not the end of the job: the fixer services are free,
rate-limited and occasionally down, so a link can land with no embed at all. After
each repost we look back at the message and, if Discord drew nothing, retry the
link on the rule's spare fixer (see :meth:`Reposter._check_embed`).
"""

from __future__ import annotations

import asyncio
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


def _same_link(a: str, b: str) -> bool:
    """Compare two URLs the way Discord echoes them back — case- and slash-insensitively."""
    return a.rstrip("/").casefold() == b.rstrip("/").casefold()


class _Repost:
    """A message we posted, plus the two operations the embed check needs on it.

    Webhook and reply mode reach the same message through different APIs, so this
    hides which one we used behind ``refetch``/``edit``.
    """

    def __init__(
        self,
        message: discord.Message,
        webhook: discord.Webhook | None = None,
        thread: discord.Thread | None = None,
    ) -> None:
        self._message = message
        self._webhook = webhook
        self._thread = thread

    async def refetch(self) -> discord.Message:
        """Re-read the message from Discord so we see embeds added after we posted."""
        if self._webhook is not None:
            return await self._webhook.fetch_message(
                self._message.id, thread=self._thread or discord.utils.MISSING
            )
        return await self._message.channel.fetch_message(self._message.id)

    async def edit(self, content: str) -> None:
        if self._webhook is not None:
            await self._webhook.edit_message(
                self._message.id,
                content=content,
                allowed_mentions=_NO_MENTIONS,
                thread=self._thread or discord.utils.MISSING,
            )
            return
        await self._message.edit(content=content, allowed_mentions=_NO_MENTIONS)


class Reposter:
    """Reposts messages with their links fixed, per the guild's chosen strategy."""

    def __init__(self, bot: discord.Client, settings: Settings) -> None:
        self._bot = bot
        self._settings = settings
        self._webhooks: dict[int, discord.Webhook] = {}  # channel id -> our webhook
        # asyncio keeps only weak references to tasks, so an un-held task can be
        # garbage-collected mid-sleep. Hold them until they finish.
        self._checks: set[asyncio.Task[None]] = set()

    async def handle(
        self, message: discord.Message, result: RewriteResult, cfg: GuildConfig
    ) -> None:
        """Repost ``message`` with its links fixed, honouring the guild's settings."""
        assert message.guild is not None  # on_message only forwards guild messages
        perms = message.channel.permissions_for(message.guild.me)

        if self._webhook_allowed(message, cfg, result, perms):
            repost = await self._repost_as_author(message, result.text)
            if repost is not None:
                if cfg.delete_original:
                    await self._delete(message)
                self._schedule_embed_check(result, repost)
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

    async def _repost_as_author(self, message: discord.Message, content: str) -> _Repost | None:
        """Send ``content`` as the author via webhook. Returns the post, or ``None``."""
        channel = message.channel
        thread = channel if isinstance(channel, discord.Thread) else None
        host = channel.parent if thread else channel
        if host is None:  # a thread whose parent we can't see — fall back to a reply
            return None

        try:
            webhook = await self._webhook_for(host)
            sent = await webhook.send(
                content=content or None,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                files=await self._copy_attachments(message),
                allowed_mentions=_NO_MENTIONS,
                thread=thread or discord.utils.MISSING,
                wait=True,  # we need the message back to check its embed later
            )
            return _Repost(sent, webhook=webhook, thread=thread)
        except (discord.Forbidden, discord.HTTPException):
            log.warning("webhook repost failed in channel %s; replying instead", channel.id)
            return None

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
            sent = await message.reply(
                fixed_links, mention_author=False, allowed_mentions=_NO_MENTIONS
            )
            self._schedule_embed_check(result, _Repost(sent))

    # ------------------------------------------------------------------ embeds

    def _schedule_embed_check(self, result: RewriteResult, repost: _Repost) -> None:
        """Queue a look-back at ``repost`` if any of its links has a spare fixer."""
        if not self._settings.embed_fallback or not result.fallbacks:
            return
        task = asyncio.create_task(self._check_embed(result, repost))
        self._checks.add(task)
        task.add_done_callback(self._checks.discard)

    async def _check_embed(self, result: RewriteResult, repost: _Repost) -> None:
        """Retry on the spare fixer any link Discord failed to draw an embed for.

        Discord crawls a link *after* the message is posted, so we wait, re-read the
        message, and compare the embeds it ended up with against the links that have
        a spare. Anything missing gets swapped and the message edited in place.

        We look more than once: a crawl that is merely slow must not cost us the
        primary fixer's better click-through, so a swap only happens once every
        attempt has come back empty.
        """
        try:
            for _ in range(max(1, self._settings.embed_check_attempts)):
                await asyncio.sleep(self._settings.embed_check_delay)
                posted = await repost.refetch()
                embedded = [embed.url for embed in posted.embeds if embed.url]
                missing = {
                    fixed: spare
                    for fixed, spare in result.fallbacks.items()
                    if not any(_same_link(url, fixed) for url in embedded)
                }
                if not missing:
                    return  # Discord got there on its own

            content = posted.content
            for fixed, spare in missing.items():
                content = content.replace(fixed, spare)
            if content == posted.content:  # the link is no longer in the message
                return

            await repost.edit(content)
            log.info("no embed for %s; retried on the fallback fixer", ", ".join(sorted(missing)))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            # The message was deleted, or we lost the permission to touch it. Either
            # way the fix is best-effort — never let it surface as a bot error.
            log.debug("embed check skipped: %s", exc)
        except Exception:
            log.exception("embed check failed")

    @staticmethod
    async def _delete(message: discord.Message) -> None:
        with contextlib.suppress(discord.HTTPException):
            await message.delete()
