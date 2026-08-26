"""The site-rules table: which links get rewritten, and to what.

Each :class:`SiteRule` maps a set of source domains to a single fixer domain.
A link is rewritten only when its host matches one of ``domains`` **and** its
path matches ``path_re`` — so profile/home links are left alone and only actual
content (a post, video, reel, …) is fixed.

Adding a platform is one entry in ``SITES``. Fixer-domain choices are seeded from
FixTweetBot's ``src/websites.py`` (MIT + Commons Clause; data reused with credit —
see NOTICE). We deliberately ship only the simple domain-swap fixers here; the
EmbedEZ-wrapped ones (Snapchat, Pinterest, Imgur, imageboards, …) use a different
URL scheme and are intentionally left for a future release.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SiteRule:
    """A single source→fixer rewrite rule."""

    id: str
    name: str
    domains: tuple[str, ...]
    fix_domain: str
    #: Regex searched against ``path[?query]``; must match for a rewrite to happen.
    path_re: re.Pattern[str] = field(compare=False)
    #: Drop the query string from the fixed URL. For platforms whose share links
    #: carry only tracking cruft (Instagram's ``?igsh=``), the query is noise.
    strip_query: bool = False
    #: A second fixer to retry with when Discord renders no embed for ``fix_domain``.
    #: Fixers are free services that rate-limit and go down; a spare keeps the video
    #: playing on the bad days without giving up the primary's nicer click-through.
    fallback_domain: str | None = None


def _compile(pattern: str) -> re.Pattern[str]:
    """Compile a case-insensitive path pattern for a :class:`SiteRule`."""
    return re.compile(pattern, re.IGNORECASE)


# Generic "this looks like content, not a profile/home page": at least two path
# segments (e.g. /track/xxxx, /view/123, /video/BVxx). Used for platforms whose
# content URLs are uniform enough that a specific pattern buys little.
_TWO_SEGMENTS = _compile(r"^/[^/]+/[^/]+")


SITES: tuple[SiteRule, ...] = (
    SiteRule(
        id="twitter",
        name="X (Twitter)",
        domains=("twitter.com", "x.com", "nitter.net", "xcancel.com"),
        fix_domain="fxtwitter.com",
        path_re=_compile(r"/status(?:es)?/\d+"),
    ),
    SiteRule(
        id="instagram",
        name="Instagram",
        domains=("instagram.com",),
        fix_domain="kkinstagram.com",
        path_re=_compile(r"/(?:p|reel|reels|tv|share)/[\w.-]+"),
        # Share links append ?igsh=<tracking token>; nothing in the query is useful.
        strip_query=True,
    ),
    SiteRule(
        id="tiktok",
        name="TikTok",
        domains=("tiktok.com",),
        fix_domain="tnktok.com",
        path_re=_compile(r"/(?:@[\w.-]+/(?:video|photo)/\d+|t/[\w-]+|v/\d+|embed/\d+)"),
        # tnktok redirects humans to the real TikTok page, so it stays primary;
        # tiktokez (EmbedEZ) embeds reliably but lands clicks on its own download
        # page, which makes it a good spare rather than a good default.
        fallback_domain="tiktokez.com",
    ),
    SiteRule(
        id="reddit",
        name="Reddit",
        domains=("reddit.com", "redditmedia.com"),
        fix_domain="vxreddit.com",
        path_re=_compile(r"/(?:r/[\w-]+/(?:comments|s)/\w+|comments/\w+|s/\w+)"),
    ),
    SiteRule(
        id="bluesky",
        name="Bluesky",
        domains=("bsky.app",),
        fix_domain="fxbsky.app",
        path_re=_compile(r"/profile/[\w.:%-]+/post/\w+"),
    ),
    SiteRule(
        id="pixiv",
        name="Pixiv",
        domains=("pixiv.net",),
        fix_domain="phixiv.net",
        path_re=_compile(r"/(?:en/)?artworks/\d+"),
    ),
    SiteRule(
        id="tumblr",
        name="Tumblr",
        domains=("tumblr.com",),
        fix_domain="tpmblr.com",
        path_re=_compile(r"/post/\d+|/[\w-]+/\d+"),
    ),
    SiteRule(
        id="deviantart",
        name="DeviantArt",
        domains=("deviantart.com",),
        fix_domain="fixdeviantart.com",
        path_re=_TWO_SEGMENTS,
    ),
    SiteRule(
        id="newgrounds",
        name="Newgrounds",
        domains=("newgrounds.com",),
        fix_domain="fixnewgrounds.com",
        path_re=_TWO_SEGMENTS,
    ),
    SiteRule(
        id="facebook",
        name="Facebook",
        domains=("facebook.com", "fb.watch"),
        fix_domain="facebed.com",
        path_re=_compile(r"/(?:share/[rvp]/[\w-]+|reel/\d+|watch|[\w.]+/(?:videos|posts)/\w+|\w+)"),
    ),
    SiteRule(
        id="bilibili",
        name="BiliBili",
        domains=("bilibili.com", "b23.tv"),
        fix_domain="vxbilibili.com",
        path_re=_compile(r"/video/[\w-]+|^/[\w-]{6,}$"),
    ),
    SiteRule(
        id="twitch",
        name="Twitch Clips",
        domains=("twitch.tv", "clips.twitch.tv"),
        fix_domain="fxtwitch.seria.moe",
        path_re=_compile(r"/\w+/clip/[\w-]+|^/[\w-]{6,}$|/videos/\d+"),
    ),
    SiteRule(
        id="spotify",
        name="Spotify",
        domains=("spotify.com",),
        fix_domain="fxspotify.com",
        path_re=_compile(r"/(?:intl-\w+/)?(?:track|album|playlist|episode|artist)/\w+"),
    ),
    SiteRule(
        id="furaffinity",
        name="Fur Affinity",
        domains=("furaffinity.net",),
        fix_domain="xfuraffinity.net",
        path_re=_compile(r"/view/\d+"),
    ),
)


def iter_domains() -> list[tuple[str, str]]:
    """Return ``(domain, site_id)`` pairs — handy for tests and the sync script."""
    return [(domain, rule.id) for rule in SITES for domain in rule.domains]
