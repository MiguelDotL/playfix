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
        # Instagram content — the ?igsh= share tracker is stripped.
        ("https://instagram.com/reel/CxYz", "https://kkinstagram.com/reel/CxYz"),
        ("https://www.instagram.com/p/AbC-1/", "https://kkinstagram.com/p/AbC-1/"),
        (
            "https://www.instagram.com/reel/CxYz/?igsh=MzRlODBiNWFlZA%3D%3D",
            "https://kkinstagram.com/reel/CxYz/",
        ),
        (
            "https://instagram.com/p/AbC-1/?igsh=x&utm_source=ig_web_copy_link",
            "https://kkinstagram.com/p/AbC-1/",
        ),
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


def test_instagram_query_stripped_other_sites_keep_it() -> None:
    """strip_query is per-rule: Instagram drops the query, X keeps it."""
    assert (
        rewrite_url("https://instagram.com/p/AbC/?igsh=tracking")
        == "https://kkinstagram.com/p/AbC/"
    )
    assert rewrite_url("https://x.com/a/status/1?s=20") == "https://fxtwitter.com/a/status/1?s=20"


def test_instagram_stripped_url_is_idempotent() -> None:
    once = rewrite_url("https://www.instagram.com/reel/CxYz/?igsh=abc")
    assert once == "https://kkinstagram.com/reel/CxYz/"
    assert rewrite_url(once) is None


def test_text_instagram_tracker_stripped_in_message() -> None:
    res = rewrite_text("look https://www.instagram.com/reel/CxYz/?igsh=abc123 nice")
    assert res.text == "look https://kkinstagram.com/reel/CxYz/ nice"
