"""The embed fallback: when a fixer fails to show the video, retry it on its spare."""

from __future__ import annotations

import asyncio

import pytest

from playfix.config import Settings
from playfix.repost import Reposter, _is_refusal, _same_link
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


def test_facebook_declares_a_spare_fixer() -> None:
    """facebed.com drew no embed on 2026-09-28 where facebed.seria.moe played."""
    facebook = next(rule for rule in SITES if rule.id == "facebook")
    assert facebook.fix_domain == "facebed.seria.moe"
    assert facebook.fallback_domain == "facebed.com"


def test_rewrite_records_the_spare_for_facebook() -> None:
    res = rewrite_text("https://www.facebook.com/reel/1502739275232354")
    assert res.fallbacks == {
        "https://facebed.seria.moe/reel/1502739275232354": (
            "https://facebed.com/reel/1502739275232354"
        )
    }


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
    def __init__(
        self, url: str | None, title: str | None = None, description: str | None = None
    ) -> None:
        self.url = url
        self.title = title
        self.description = description


def refusal_embed(url: str | None) -> FakeEmbed:
    """The card tnktok.com serves for an age-restricted TikTok (captured 2026-09-26).

    Its page carries no ``og:url``, so Discord may or may not attach one to the
    embed — the check must catch it either way; see the two tests below.
    """
    return FakeEmbed(
        url,
        title="⚠️ Sensitive Content",
        description=(
            "Sorry, we were unable to show this video due to the video being "
            "age-restricted. If you would like to view the video, please visit "
            "TikTok directly."
        ),
    )


class FakePosted:
    def __init__(self, content: str, embeds: list[FakeEmbed]) -> None:
        self.content = content
        self.embeds = embeds


class FakeRepost:
    """Stands in for a posted message: hands back ``posted``, records every edit.

    Pass several states to model a crawl that lands late — each ``refetch`` returns
    the next one, then repeats the last. ``after_swap`` is what Discord makes of the
    message once the check has edited it to the spare; leave it out to model a spare
    that draws nothing either.
    """

    def __init__(self, *posted: FakePosted, after_swap: FakePosted | None = None) -> None:
        self._posted = list(posted)
        self._after_swap = after_swap
        self._swapped = False
        self.fetches = 0
        self.fetches_after_swap = 0
        self.edits: list[str] = []

    @property
    def edited_to(self) -> str | None:
        """The content the message was left with, or ``None`` if never edited."""
        return self.edits[-1] if self.edits else None

    async def refetch(self) -> FakePosted:
        if self._swapped:
            self.fetches_after_swap += 1
            return self._after_swap or FakePosted(self.edits[-1], [])
        state = self._posted[min(self.fetches, len(self._posted) - 1)]
        self.fetches += 1
        return state

    async def edit(self, content: str) -> None:
        self.edits.append(content)
        self._swapped = True


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
    repost = FakeRepost(FakePosted(FIXED, []), after_swap=FakePosted(SPARE, [FakeEmbed(SPARE)]))
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == SPARE


def test_an_unrelated_embed_does_not_count_as_success() -> None:
    """A second link embedding fine must not mask the TikTok link drawing nothing."""
    result = rewrite_text(f"{TIKTOK} https://x.com/a/status/1")
    other = "https://fxtwitter.com/a/status/1"
    repost = FakeRepost(
        FakePosted(f"{FIXED} {other}", [FakeEmbed(other)]),
        after_swap=FakePosted(f"{SPARE} {other}", [FakeEmbed(SPARE), FakeEmbed(other)]),
    )
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == f"{SPARE} {other}"


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
    repost = FakeRepost(FakePosted(FIXED, []), after_swap=FakePosted(SPARE, [FakeEmbed(SPARE)]))
    reposter = make_reposter()
    asyncio.run(reposter._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.fetches == reposter._settings.embed_check_attempts
    assert repost.edited_to == SPARE


# ------------------------------------------------------------ refusal cards


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("⚠️ Sensitive Content", "…the video being age-restricted…", True),
        (None, "Sorry, we were unable to show this video.", True),
        ("SENSITIVE CONTENT", None, True),  # matching must ignore case
        ("This post is private", None, True),
        ("Author Myron J Clifton (@deardean22)", "#fyp", False),
        (None, None, False),
    ],
)
def test_is_refusal(title: str | None, description: str | None, expected: bool) -> None:
    assert _is_refusal(FakeEmbed(FIXED, title, description)) is expected  # type: ignore[arg-type]


def test_a_refusal_card_with_a_url_still_counts_as_no_video() -> None:
    """An age-restricted TikTok embeds an apology, not the video — retry the spare."""
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(
        FakePosted(FIXED, [refusal_embed(FIXED)]),
        after_swap=FakePosted(SPARE, [FakeEmbed(SPARE)]),
    )
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == SPARE


def test_a_refusal_card_without_a_url_also_counts_as_no_video() -> None:
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(
        FakePosted(FIXED, [refusal_embed(None)]),
        after_swap=FakePosted(SPARE, [FakeEmbed(SPARE)]),
    )
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == SPARE


def test_a_refusal_on_one_link_does_not_swap_a_link_that_played() -> None:
    """Only the refused link is retried; a working neighbour is left alone."""
    result = rewrite_text(f"{TIKTOK} https://x.com/a/status/1")
    other = "https://fxtwitter.com/a/status/1"
    repost = FakeRepost(
        FakePosted(f"{FIXED} {other}", [refusal_embed(FIXED), FakeEmbed(other, "a post")]),
        after_swap=FakePosted(f"{SPARE} {other}", [FakeEmbed(SPARE), FakeEmbed(other)]),
    )
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == f"{SPARE} {other}"


# --------------------------------------------- when the spare fails as well


def embedez_failure_embed(url: str | None) -> FakeEmbed:
    """What tiktokez.com served for an age-restricted TikTok on 2026-09-29."""
    return FakeEmbed(url, title="Failed to Get Post | EmbedEZ")


def test_the_primary_is_restored_when_the_spare_draws_nothing_either() -> None:
    """A bare link to a dead spare says less than the primary's "age-restricted" card."""
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(FakePosted(FIXED, [refusal_embed(FIXED)]))  # spare fails too
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edits == [SPARE, FIXED]  # swapped, then put back
    assert repost.edited_to == FIXED
    # One look, not two: the spare was reached only after the primary had already
    # been given every attempt, so there is no slow-crawl benefit of the doubt left
    # to give — and a second wait leaves a dead link on screen for twice as long.
    assert repost.fetches_after_swap == 1


def test_the_primary_is_restored_when_the_spare_serves_its_own_error_card() -> None:
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(
        FakePosted(FIXED, [refusal_embed(FIXED)]),
        after_swap=FakePosted(SPARE, [embedez_failure_embed(SPARE)]),
    )
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edited_to == FIXED


def test_a_working_spare_is_never_undone() -> None:
    result = rewrite_text(TIKTOK)
    repost = FakeRepost(
        FakePosted(FIXED, [refusal_embed(FIXED)]),
        after_swap=FakePosted(SPARE, [FakeEmbed(SPARE)]),
    )
    asyncio.run(make_reposter()._check_embed(result, repost))  # type: ignore[arg-type]
    assert repost.edits == [SPARE]
