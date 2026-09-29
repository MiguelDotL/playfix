"""Post the fixed version of a message back to its channel.

Each guild picks one of two strategies:

* ``webhook`` (default) — repost the message through a channel webhook using the
  author's name and avatar, then delete the original, so the fix looks like it came
  from them. Requires *Manage Webhooks* and *Manage Messages*.
* ``reply`` — leave the original in place, suppress its broken preview, and reply
  with the fixed links. Non-destructive, and used automatically as a fallback when
  the bot lacks the permissions webhook mode needs.

Posting the fixed link is not the end of the job: the fixer services are free,
rate-limited and occasionally down, so a link can land with no embed at all — or
with an embed that is only the fixer apologising. After each repost we look back at
the message and, if the video did not actually show up, retry the link on the rule's
spare fixer (see :meth:`Reposter._check_embed`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Iterable
from typing import Any

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


# When the source refuses a fixer — an age-restricted or private TikTok, a deleted
# post, a login wall — the fixer answers 200 with a stub page carrying only an
# apology in its OpenGraph tags. Discord draws that stub as a perfectly normal
# embed, so "the message has an embed" is not the same as "the video plays": we
# have to read the card to tell a fix from an apology. Matched case-insensitively
# against the embed's title and description.
_REFUSAL_PHRASES = (
    "sensitive content",
    "age-restricted",
    "age restricted",
    "unable to show this video",
    "unable to load",
    "this post is private",
    "failed to get post",  # EmbedEZ's wording
)


def _is_refusal(embed: discord.Embed) -> bool:
    """True when an embed is a fixer's "sorry, no video" card rather than the media."""
    card = f"{embed.title or ''}\n{embed.description or ''}".casefold()
    return any(phrase in card for phrase in _REFUSAL_PHRASES)


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

    async def _look(
        self, repost: _Repost, links: Iterable[str], attempts: int
    ) -> tuple[Any, set[str]]:
        """Re-read ``repost`` and return it with the subset of ``links`` that drew no media.

        Discord crawls a link *after* the message is posted, so each look is preceded
        by a wait. A link counts as fixed only if it drew an embed that is actually
        the media: a refusal card (see :func:`_is_refusal`) is treated the same as no
        embed at all, because to the reader it is the same failure.

        We look more than once where it matters: a crawl that is merely slow must not
        cost us the primary fixer's better click-through, so the caller only acts once
        every attempt has come back empty.
        """
        wanted = list(links)
        missing: set[str] = set(wanted)
        posted = None
        for _ in range(max(1, attempts)):
            await asyncio.sleep(self._settings.embed_check_delay)
            posted = await repost.refetch()
            embedded = [
                embed.url for embed in posted.embeds if embed.url and not _is_refusal(embed)
            ]
            missing = {
                link for link in wanted if not any(_same_link(url, link) for url in embedded)
            }
            if not missing:
                break
        return posted, missing

    async def _check_embed(self, result: RewriteResult, repost: _Repost) -> None:
        """Retry on the spare fixer any link that did not end up playing.

        Anything the primary fixer failed to draw gets swapped to that site's spare
        and the message edited in place. The spare is a free service too, though, and
        can be just as dead — so we look once more afterwards and put the primary back
        if the spare drew nothing either. The primary's own error card at least says
        *why* there is no video ("age-restricted", "this post is private"); a bare link
        to a second fixer that also failed says nothing at all.
        """
        try:
            posted, failed = await self._look(
                repost, result.fallbacks, self._settings.embed_check_attempts
            )
            if not failed:
                return  # Discord got there on its own

            primary_text = posted.content
            content = primary_text
            for fixed in failed:
                content = content.replace(fixed, result.fallbacks[fixed])
            if content == primary_text:  # the link is no longer in the message
                return

            await repost.edit(content)
            log.info("no video for %s; retried on the fallback fixer", ", ".join(sorted(failed)))

            spares = [result.fallbacks[fixed] for fixed in failed]
            _, still_failed = await self._look(repost, spares, attempts=1)
            if still_failed:
                await repost.edit(primary_text)
                log.info(
                    "the spare drew nothing either for %s; restored the primary",
                    ", ".join(sorted(still_failed)),
                )
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
