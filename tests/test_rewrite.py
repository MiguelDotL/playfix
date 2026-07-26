"""Behavioural tests for the pure rewrite engine."""

import pytest

from playfix.rewrite import rewrite_text, rewrite_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # X / Twitter — status links get fixed, on every host variant.
        ("https://x.com/jack/status/20", "https://fxtwitter.com/jack/status/20"),
        ("https://twitter.com/jack/status/20", "https://fxtwitter.com/jack/status/20"),
        ("https://www.x.com/jack/status/20", "https://fxtwitter.com/jack/status/20"),
        ("https://mobile.twitter.com/a/status/1", "https://fxtwitter.com/a/status/1"),
        ("https://x.com/i/web/status/123", "https://fxtwitter.com/i/web/status/123"),
        # Query string + tracking params are preserved.
        (
            "https://x.com/a/status/1?s=20&t=abc",
            "https://fxtwitter.com/a/status/1?s=20&t=abc",
        ),
        # Instagram content.
        ("https://instagram.com/reel/CxYz", "https://fxstagram.com/reel/CxYz"),
        ("https://www.instagram.com/p/AbC-1/", "https://fxstagram.com/p/AbC-1/"),
        # TikTok content.
        (
            "https://www.tiktok.com/@user.name/video/7300000000000000000",
            "https://tnktok.com/@user.name/video/7300000000000000000",
        ),
        # Reddit content (old + share forms).
        (
            "https://reddit.com/r/aww/comments/abc123/title/",
            "https://vxreddit.com/r/aww/comments/abc123/title/",
        ),
        ("https://www.reddit.com/r/aww/s/xY9", "https://vxreddit.com/r/aww/s/xY9"),
        # Bluesky.
        (
            "https://bsky.app/profile/alice.bsky.social/post/3k",
            "https://fxbsky.app/profile/alice.bsky.social/post/3k",
        ),
    ],
)
def test_rewrite_url_hits(url: str, expected: str) -> None:
    assert rewrite_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/home",  # not content
        "https://x.com/jack",  # profile
        "https://instagram.com/nasa",  # profile
        "https://example.com/x/status/1",  # unrelated host
        "https://fxtwitter.com/a/status/1",  # already fixed — must be idempotent
        "https://youtube.com/watch?v=abc",  # deliberately unsupported (Discord embeds it)
        "not a url at all",
    ],
)
def test_rewrite_url_misses(url: str) -> None:
    assert rewrite_url(url) is None


def test_idempotent() -> None:
    once = rewrite_url("https://x.com/a/status/1")
    assert once is not None
    assert rewrite_url(once) is None


def test_text_single_link_with_caption() -> None:
    res = rewrite_text("check this out https://x.com/a/status/1 lol")
    assert res.changed
    assert res.text == "check this out https://fxtwitter.com/a/status/1 lol"
    assert res.rewrites == [("https://x.com/a/status/1", "https://fxtwitter.com/a/status/1")]


def test_text_trailing_punctuation_preserved() -> None:
    res = rewrite_text("wow https://x.com/a/status/1.")
    assert res.text == "wow https://fxtwitter.com/a/status/1."


def test_text_markdown_parens_preserved() -> None:
    res = rewrite_text("see (https://x.com/a/status/1)")
    assert res.text == "see (https://fxtwitter.com/a/status/1)"


def test_text_multiple_mixed_links() -> None:
    res = rewrite_text(
        "https://x.com/a/status/1 and https://example.com and "
        "https://www.tiktok.com/@u/video/7300000000000000000"
    )
    assert len(res.rewrites) == 2
    assert "fxtwitter.com/a/status/1" in res.text
    assert "tnktok.com/@u/video/7300000000000000000" in res.text
    assert "https://example.com" in res.text  # untouched


def test_text_no_links_unchanged() -> None:
    res = rewrite_text("just a normal message, nothing to fix")
    assert not res.changed
    assert res.text == "just a normal message, nothing to fix"
