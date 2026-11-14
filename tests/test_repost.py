"""When to repost as the author, and keeping that repost from losing anything."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from playfix.config import Settings
from playfix.db import GuildConfig
from playfix.repost import WEBHOOK_NAME, Reposter
from playfix.rewrite import rewrite_text

MB = 1024 * 1024
LINK = "https://x.com/a/status/1"


def make_reposter(**settings: object) -> Reposter:
    bot = SimpleNamespace(user=object())
    return Reposter(bot=bot, settings=Settings(PLAYFIX_TOKEN="test-token", **settings))  # type: ignore[arg-type]


def make_channel(channel_id: int = 1) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.webhooks = AsyncMock(return_value=[])
    return channel


def make_message(
    *,
    kind: discord.MessageType = discord.MessageType.default,
    attachments: list[object] | None = None,
    filesize_limit: int = 10 * MB,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=99,
        type=kind,
        attachments=attachments or [],
        channel=make_channel(),
        guild=SimpleNamespace(filesize_limit=filesize_limit),
        author=SimpleNamespace(
            display_name="someone", display_avatar=SimpleNamespace(url="https://a/b.png")
        ),
    )


def attachment(size: int, *, fails: bool = False) -> MagicMock:
    att = MagicMock(spec=discord.Attachment)
    att.size = size
    if fails:
        att.to_file = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "x"))
    else:
        att.to_file = AsyncMock(return_value=MagicMock(spec=discord.File))
    return att


def allowed(reposter: Reposter, message: SimpleNamespace) -> bool:
    perms = SimpleNamespace(manage_webhooks=True, manage_messages=True)
    cfg = GuildConfig(guild_id=1, enabled=True, mode="webhook", delete_original=True)
    return reposter._webhook_allowed(message, cfg, rewrite_text(LINK), perms)  # type: ignore[arg-type]


# ------------------------------------------------------------ webhook or reply


def test_a_plain_message_is_reposted_as_the_author() -> None:
    assert allowed(make_reposter(), make_message())


def test_a_reply_is_answered_in_place_so_it_stays_attached_to_its_thread() -> None:
    assert not allowed(make_reposter(), make_message(kind=discord.MessageType.reply))


def test_an_attachment_too_big_to_reupload_keeps_the_original() -> None:
    message = make_message(attachments=[attachment(12 * MB)], filesize_limit=10 * MB)
    assert not allowed(make_reposter(), message)


def test_our_own_cap_applies_when_lower_than_the_guilds() -> None:
    message = make_message(attachments=[attachment(6 * MB)], filesize_limit=100 * MB)
    assert not allowed(make_reposter(max_attachment_mb=5), message)


def test_an_attachment_within_both_limits_is_carried_over() -> None:
    message = make_message(attachments=[attachment(9 * MB)], filesize_limit=10 * MB)
    assert allowed(make_reposter(), message)


# ---------------------------------------------------------------- attachments


def test_attachments_copy_all_or_nothing() -> None:
    reposter = make_reposter()
    ok = make_message(attachments=[attachment(1), attachment(1)])
    assert len(asyncio.run(reposter._copy_attachments(ok))) == 2  # type: ignore[arg-type]

    broken = make_message(attachments=[attachment(1), attachment(1, fails=True)])
    assert asyncio.run(reposter._copy_attachments(broken)) is None  # type: ignore[arg-type]


def test_a_failed_attachment_copy_falls_back_instead_of_posting_without_it() -> None:
    reposter = make_reposter()
    message = make_message(attachments=[attachment(1, fails=True)])
    webhook = MagicMock(send=AsyncMock())
    reposter._webhooks[message.channel.id] = webhook
    assert asyncio.run(reposter._repost_as_author(message, LINK)) is None  # type: ignore[arg-type]
    webhook.send.assert_not_called()


# --------------------------------------------------------------- stale webhook


def not_found() -> discord.NotFound:
    return discord.NotFound(MagicMock(status=404, reason="Not Found"), "Unknown Webhook")


def test_a_deleted_webhook_is_replaced_and_the_repost_still_goes_out() -> None:
    reposter = make_reposter()
    message = make_message()
    dead = MagicMock(send=AsyncMock(side_effect=not_found()))
    fresh = MagicMock(send=AsyncMock(return_value=MagicMock()))
    fresh.name = WEBHOOK_NAME
    reposter._webhooks[message.channel.id] = dead
    message.channel.create_webhook = AsyncMock(return_value=fresh)

    repost = asyncio.run(reposter._repost_as_author(message, LINK))  # type: ignore[arg-type]

    assert repost is not None
    fresh.send.assert_awaited_once()
    assert reposter._webhooks[message.channel.id] is fresh


@pytest.mark.parametrize("second", ["not_found", "forbidden"])
def test_gives_up_after_one_retry(second: str) -> None:
    reposter = make_reposter()
    message = make_message()
    dead = MagicMock(send=AsyncMock(side_effect=not_found()))
    error = (
        not_found()
        if second == "not_found"
        else discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "nope")
    )
    also_dead = MagicMock(send=AsyncMock(side_effect=error))
    reposter._webhooks[message.channel.id] = dead
    message.channel.create_webhook = AsyncMock(return_value=also_dead)

    assert asyncio.run(reposter._repost_as_author(message, LINK)) is None  # type: ignore[arg-type]
    assert also_dead.send.await_count == 1
