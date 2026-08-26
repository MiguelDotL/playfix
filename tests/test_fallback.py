"""The embed fallback: when a fixer draws no embed, retry the link on its spare."""

from __future__ import annotations

import asyncio

import pytest

from playfix.config import Settings
from playfix.repost import Reposter, _same_link
from playfix.rewrite import rewrite_text
from playfix.sites import SITES

TIKTOK = "https://www.tiktok.com/@someone/video/7678001595837107486"
FIXED = "https://tnktok.com/@someone/video/7678001595837107486"
SPARE = "https://tiktokez.com/@someone/video/7678001595837107486"


# --------------------------------------------------------------------- rules


def test_tiktok_declares_a_spare_fixer() -> None:
    tiktok = next(rule for rule in SITES if rule.id == "tiktok")
    assert tiktok.fix_domain == "tnktok.com"
    assert tiktok.fallback_domain == "tiktokez.com"


def test_a_spare_never_equals_the_primary() -> None:
    for rule in SITES:
        assert rule.fallback_domain != rule.fix_domain


# ------------------------------------------------------------------ rewrites


def test_rewrite_records_the_spare_for_tiktok() -> None:
    res = rewrite_text(f"look {TIKTOK}")
    assert res.text == f"look {FIXED}"
    assert res.fallbacks == {FIXED: SPARE}


def test_rewrite_records_no_spare_for_sites_without_one() -> None:
    res = rewrite_text("https://x.com/a/status/1")
    assert res.changed
    assert res.fallbacks == {}


def test_fallback_text_swaps_only_the_fallback_capable_link() -> None:
    res = rewrite_text(f"{TIKTOK} and https://x.com/a/status/1")
    assert res.fallback_text() == f"{SPARE} and https://fxtwitter.com/a/status/1"


# ------------------------------------------------------------- link matching


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (FIXED, FIXED, True),
        (FIXED + "/", FIXED, True),
        (FIXED.upper(), FIXED, True),
        (FIXED, SPARE, False),
    ],
)
def test_same_link(a: str, b: str, expected: bool) -> None:
    assert _same_link(a, b) is expected


# --------------------------------------------------------------- embed check


class FakeEmbed:
    def __init__(self, url: str | None) -> None:
        self.url = url


class FakePosted:
    def __init__(self, content: str, embeds: list[FakeEmbed]) -> None:
        self.content = content
        self.embeds = embeds


class FakeRepost:
    """Stands in for a posted message: hands back ``posted``, records any edit.

    Pass several states to model a crawl that lands late — each ``refetch`` returns
    the next one, then repeats the last.
    """

    def __init__(self, *posted: FakePosted) -> None:
        self._posted = list(posted)
        self.fetches = 0
        self.edited_to: str | None = None

    async def refetch(self) -> FakePosted:
        state = self._posted[min(self.fetches, len(self._posted) - 1)]
        self.fetches += 1
        return state

    async def edit(self, content: str) -> None:
        self.edited_to = content


def make_reposter() -> Reposter:
    """A Reposter whose embed check fires immediately instead of after a wait."""
    settings = Settings(PLAYFIX_TOKEN="test-token", embed_check_delay=0.0)
    return Reposter(bot=None, settings=settings)  # type: ignore[arg-type]


def test_no_edit_when_the_embed_landed() -> None:
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(FakePosted(FIXED, [FakeEmbed(FIXED)]))
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to is None


def test_swaps_to_the_spare_when_no_embed_landed() -> None:
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(FakePosted(FIXED, []))
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == SPARE


def test_an_unrelated_embed_does_not_count_as_success() -> None:
    """A second link embedding fine must not mask the TikTok link drawing nothing."""
    result = rewrite_text(f"{TIKTOK} https://x.com/a/status/1")
    posted = FakePosted(
        f"{FIXED} https://fxtwitter.com/a/status/1",
        [FakeEmbed("https://fxtwitter.com/a/status/1")],
    )
    repost = FakeRepost(posted)
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == f"{SPARE} https://fxtwitter.com/a/status/1"


def test_no_edit_when_the_link_is_gone_from_the_message() -> None:
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(FakePosted("someone edited this", []))
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to is None


def test_a_late_embed_on_the_second_look_prevents_a_swap() -> None:
    """A slow crawl must not cost us the primary fixer's better click-through."""
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(
        FakePosted(FIXED, []),  # first look: Discord hasn't crawled it yet
        FakePosted(FIXED, [FakeEmbed(FIXED)]),  # second look: the embed landed
    )
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to is None
    assert repost.fetches == 2


def test_swap_only_after_every_attempt_comes_back_empty() -> None:
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(FakePosted(FIXED, []))
    reposter = make_reposter()
    asyncio.run(reposter._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.fetches == reposter._settings.embed_check_attempts
    assert repost.edited_to == SPARE
