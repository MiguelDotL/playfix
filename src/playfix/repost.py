"""Turn a message with fixable links into a playable one.

Two strategies, chosen per guild:

* **webhook** (default) — repost the message via a channel webhook under the
  author's name + avatar, then delete the original. The fixed embed looks like it
  came from them. Requires *Manage Webhooks* + *Manage Messages*.
* **reply** — leave the original, suppress its broken embed, and reply with the
  fixed links. The safe, non-destructive fallback (also used automatically when the
  bot lacks the permissions for webhook mode).
"""

from __future__ import annotations

import contextlib
import logging

import discord

from .db import GuildConfig
from .rewrite import RewriteResult

log = logging.getLogger(__name__)

WEBHOOK_NAME = "PlayFix"
# Never let a repost trigger pings — the author's name or pasted content must not
# be able to @everyone/@role through us.
_NO_PINGS = discord.AllowedMentions.none()


async def handle(
    bot: discord.Client,
    message: discord.Message,
    result: RewriteResult,
    cfg: GuildConfig,
    *,
    max_attachment_bytes: int,
    max_content_length: int,
) -> None:
    """Apply the configured strategy to a message that has fixable links."""
    me = message.guild.me  # type: ignore[union-attr]
    perms = message.channel.permissions_for(me)

    webhookable = isinstance(
        message.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)
    )
    want_webhook = (
        cfg.mode == "webhook"
        and perms.manage_webhooks
        and perms.manage_messages
        and webhookable
        and len(result.text) <= max_content_length
    )

    if want_webhook:
        try:
            await _repost_as_author(
                bot, message, result.text, max_attachment_bytes=max_attachment_bytes
            )
        except (discord.Forbidden, discord.HTTPException, RuntimeError):
            log.warning("webhook repost failed in %s; falling back to reply", message.channel.id)
        else:
            # Repost succeeded — remove the original (failure here is non-fatal).
            if cfg.delete_original:
                try:
                    await message.delete()
                except discord.HTTPException:
                    log.debug("could not delete original %s", message.id)
            return

    await _reply_with_fix(message, result, perms)


async def _get_webhook(bot: discord.Client, channel: discord.abc.GuildChannel) -> discord.Webhook:
    """Reuse our webhook on this channel if present, else create one (cached)."""
    cache: dict[int, discord.Webhook] = bot._playfix_webhooks  # type: ignore[attr-defined]
    if channel.id in cache:
        return cache[channel.id]
    for wh in await channel.webhooks():  # type: ignore[attr-defined]
        if wh.user and bot.user and wh.user.id == bot.user.id and wh.name == WEBHOOK_NAME:
            cache[channel.id] = wh
            return wh
    wh = await channel.create_webhook(name=WEBHOOK_NAME, reason="PlayFix embed fix")  # type: ignore[attr-defined]
    cache[channel.id] = wh
    return wh


async def _repost_as_author(
    bot: discord.Client,
    message: discord.Message,
    content: str,
    *,
    max_attachment_bytes: int,
) -> None:
    channel = message.channel
    send_kwargs: dict = {}
    if isinstance(channel, discord.Thread):
        target = channel.parent
        send_kwargs["thread"] = channel
    else:
        target = channel
    if target is None:  # e.g. a thread with no accessible parent — trigger fallback
        raise RuntimeError("no webhook-capable target channel")

    webhook = await _get_webhook(bot, target)

    files: list[discord.File] = []
    for attachment in message.attachments:
        if attachment.size <= max_attachment_bytes:
            try:
                files.append(await attachment.to_file())
            except discord.HTTPException:
                log.debug("could not re-upload attachment %s", attachment.filename)

    author = message.author
    await webhook.send(
        content=content or None,
        username=author.display_name,
        avatar_url=author.display_avatar.url,
        files=files,
        allowed_mentions=_NO_PINGS,
        **send_kwargs,
    )


async def _reply_with_fix(
    message: discord.Message, result: RewriteResult, perms: discord.Permissions
) -> None:
    if perms.manage_messages:
        with contextlib.suppress(discord.HTTPException):
            await message.edit(suppress=True)  # hide the broken original embed
    fixed_links = "\n".join(fixed for _, fixed in result.rewrites)
    try:
        await message.reply(fixed_links, mention_author=False, allowed_mentions=_NO_PINGS)
    except discord.HTTPException:
        log.exception("reply fallback failed in %s", message.channel.id)
