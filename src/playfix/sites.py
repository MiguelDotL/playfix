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


def _c(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# Generic "this looks like content, not a profile/home page": at least two path
# segments (e.g. /track/xxxx, /view/123, /video/BVxx). Used for platforms whose
# content URLs are uniform enough that a specific pattern buys little.
_TWO_SEGMENTS = _c(r"^/[^/]+/[^/]+")


SITES: tuple[SiteRule, ...] = (
    SiteRule(
        id="twitter",
        name="X (Twitter)",
        domains=("twitter.com", "x.com", "nitter.net", "xcancel.com"),
        fix_domain="fxtwitter.com",
        path_re=_c(r"/status(?:es)?/\d+"),
    ),
    SiteRule(
        id="instagram",
        name="Instagram",
        domains=("instagram.com",),
        fix_domain="fxstagram.com",
        path_re=_c(r"/(?:p|reel|reels|tv|share)/[\w.-]+"),
    ),
    SiteRule(
        id="tiktok",
        name="TikTok",
        domains=("tiktok.com",),
        fix_domain="tnktok.com",
        path_re=_c(r"/(?:@[\w.-]+/(?:video|photo)/\d+|t/[\w-]+|v/\d+|embed/\d+)"),
    ),
    SiteRule(
        id="reddit",
        name="Reddit",
        domains=("reddit.com", "redditmedia.com"),
        fix_domain="vxreddit.com",
        path_re=_c(r"/(?:r/[\w-]+/(?:comments|s)/\w+|comments/\w+|s/\w+)"),
    ),
    SiteRule(
        id="bluesky",
        name="Bluesky",
        domains=("bsky.app",),
        fix_domain="fxbsky.app",
        path_re=_c(r"/profile/[\w.:%-]+/post/\w+"),
    ),
    SiteRule(
        id="pixiv",
        name="Pixiv",
        domains=("pixiv.net",),
        fix_domain="phixiv.net",
        path_re=_c(r"/(?:en/)?artworks/\d+"),
    ),
    SiteRule(
        id="tumblr",
        name="Tumblr",
        domains=("tumblr.com",),
        fix_domain="tpmblr.com",
        path_re=_c(r"/post/\d+|/[\w-]+/\d+"),
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
        path_re=_c(r"/(?:share/[rvp]/[\w-]+|reel/\d+|watch|[\w.]+/(?:videos|posts)/\w+|\w+)"),
    ),
    SiteRule(
        id="bilibili",
        name="BiliBili",
        domains=("bilibili.com", "b23.tv"),
        fix_domain="vxbilibili.com",
        path_re=_c(r"/video/[\w-]+|^/[\w-]{6,}$"),
    ),
    SiteRule(
        id="twitch",
        name="Twitch Clips",
        domains=("twitch.tv", "clips.twitch.tv"),
        fix_domain="fxtwitch.seria.moe",
        path_re=_c(r"/\w+/clip/[\w-]+|^/[\w-]{6,}$|/videos/\d+"),
    ),
    SiteRule(
        id="spotify",
        name="Spotify",
        domains=("spotify.com",),
        fix_domain="fxspotify.com",
        path_re=_c(r"/(?:intl-\w+/)?(?:track|album|playlist|episode|artist)/\w+"),
    ),
    SiteRule(
        id="furaffinity",
        name="Fur Affinity",
        domains=("furaffinity.net",),
        fix_domain="xfuraffinity.net",
        path_re=_c(r"/view/\d+"),
    ),
    SiteRule(
        id="mastodon",
        name="Mastodon",
        domains=(
            "mastodon.social",
            "mstdn.social",
            "mastodon.world",
            "mastodon.online",
            "mas.to",
            "infosec.exchange",
        ),
        fix_domain="fx.zillanlabs.tech",
        path_re=_c(r"/@[\w.-]+/\d+"),
    ),
)


def iter_domains() -> list[tuple[str, str]]:
    """Return ``(domain, site_id)`` pairs — handy for tests and the sync script."""
    return [(d, rule.id) for rule in SITES for d in rule.domains]
