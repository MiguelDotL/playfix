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
from collections.abc import Callable
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
    #: Reshape the path for the fixer, given ``(host, path)``. For fixers whose URL
    #: layout differs from the source's (Twitch's clip subdomain, Tumblr blog hosts).
    path_fn: Callable[[str, str], str] | None = field(default=None, compare=False)


def _compile(pattern: str) -> re.Pattern[str]:
    """Compile a case-insensitive path pattern for a :class:`SiteRule`."""
    return re.compile(pattern, re.IGNORECASE)


# Generic "this looks like content, not a profile/home page": at least two path
# segments (e.g. /track/xxxx, /view/123, /video/BVxx). Used for platforms whose
# content URLs are uniform enough that a specific pattern buys little.
_TWO_SEGMENTS = _compile(r"^/[^/]+/[^/]+")


def _tumblr_path(host: str, path: str) -> str:
    """``<blog>.tumblr.com/post/<id>`` → ``/<blog>/<id>``: tpmblr 404s without the blog."""
    blog = host.split(".")[0]
    if host.count(".") >= 2 and blog != "www":
        return re.sub(r"^/post/", f"/{blog}/", path, count=1)
    return path


def _reddit_path(host: str, path: str) -> str:
    """vxreddit draws no media for ``/gallery/<id>``; the same post as ``/comments/<id>`` works."""
    return re.sub(r"^/gallery/", "/comments/", path, count=1)


SITES: tuple[SiteRule, ...] = (
    SiteRule(
        id="twitter",
        name="X (Twitter)",
        domains=("twitter.com", "x.com", "nitter.net", "xcancel.com"),
        fix_domain="fxtwitter.com",
        path_re=_compile(r"/status(?:es)?/\d+"),
        # fixupx.com is the same backend as fxtwitter, so it would fail together
        # with it; vxtwitter is a separate service.
        fallback_domain="vxtwitter.com",
    ),
    SiteRule(
        id="instagram",
        name="Instagram",
        domains=("instagram.com",),
        # kkinstagram.com hands some reels back as their cover JPEG instead of the
        # video (2026-11-13: /reel/DfcE6XrxSqB/ 302'd to a .jpg, so Discord drew a
        # still image), while vxinstagram.com served that reel's real mp4. A still
        # image still counts as "an embed", so the spare can't rescue that case —
        # the primary has to be the fixer that returns the video.
        fix_domain="vxinstagram.com",
        # zzinstagram served the real mp4 for that reel too, and sends human clicks
        # straight to instagram.com. kkinstagram (the old spare) lands them on a
        # kkclip.com page carrying popunder-ad code.
        fallback_domain="zzinstagram.com",
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
        # tnktok redirects humans to the real TikTok page, so it stays primary.
        # The spare's job is mostly age-restricted videos, where tnktok serves a
        # "⚠️ Sensitive Content" card. kktiktok 302s straight to the TikTok CDN mp4
        # even for those (3/3 measured 2026-11-14). It lands human clicks on a
        # kkclip.com "Open in App" page, which is why it isn't primary. The previous
        # spare, tiktokez.com, now sends crawlers to an EmbedEZ download page with
        # no OpenGraph tags at all.
        fallback_domain="kktiktok.com",
    ),
    SiteRule(
        id="tiktok-short",
        name="TikTok (share link)",
        # The app's share links: the code is the whole path. Only on these hosts —
        # on tiktok.com itself a one-segment path is a page like /explore.
        domains=("vm.tiktok.com", "vt.tiktok.com"),
        fix_domain="tnktok.com",
        path_re=_compile(r"^/[\w-]{6,}/?$"),
        fallback_domain="kktiktok.com",
    ),
    SiteRule(
        id="reddit",
        name="Reddit",
        domains=("reddit.com", "redditmedia.com"),
        fix_domain="vxreddit.com",
        path_re=_compile(r"/(?:r/[\w-]+/(?:comments|s)/\w+|comments/\w+|s/\w+|gallery/\w+)"),
        path_fn=_reddit_path,
    ),
    SiteRule(
        id="reddit-short",
        name="Reddit (redd.it)",
        domains=("redd.it",),
        fix_domain="vxreddit.com",
        path_re=_compile(r"^/\w+/?$"),
    ),
    SiteRule(
        id="bluesky",
        name="Bluesky",
        domains=("bsky.app",),
        fix_domain="fxbsky.app",
        path_re=_compile(r"/profile/[\w.:%-]+/post/\w+"),
        fallback_domain="bskx.app",
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
        path_fn=_tumblr_path,
    ),
    SiteRule(
        id="deviantart",
        name="DeviantArt",
        domains=("deviantart.com",),
        fix_domain="fixdeviantart.com",
        path_re=_TWO_SEGMENTS,
    ),
    SiteRule(
        id="facebook",
        name="Facebook",
        # Not fb.watch: its short codes redirect to /watch?v=<id> only on Facebook's
        # side, and facebed answers the bare code with a "Log in" card (0/3 measured
        # 2026-11-14). Those links are left alone until PlayFix resolves redirects.
        domains=("facebook.com",),
        # Both of these run the same software (facebed), and both serve the same
        # OpenGraph tags for a reel — yet on 2026-09-28 `facebed.com` reliably drew
        # no embed at all in Discord while `facebed.seria.moe` played the video, on
        # the same link, minutes apart. The metadata is identical, so whatever the
        # difference is lives between Discord's crawler and the host, not in the
        # page. Primary is the instance observed to work; the other stays as spare.
        fix_domain="facebed.seria.moe",
        fallback_domain="facebed.com",
        path_re=_compile(r"/(?:share/[rvp]/[\w-]+|reel/\d+|watch|[\w.]+/(?:videos|posts)/\w+)"),
        # NOT strip_query, tempting as the ?mibextid= share tracker is: Facebook's
        # /watch links carry the video id in the query (`/watch?v=<id>`), so dropping
        # it would rewrite them to a bare /watch. facebed ignores the tracker anyway.
    ),
    SiteRule(
        id="bilibili",
        name="BiliBili",
        domains=("bilibili.com",),
        fix_domain="vxbilibili.com",
        path_re=_compile(r"/video/[\w-]+"),
    ),
    SiteRule(
        id="bilibili-short",
        name="BiliBili (b23.tv)",
        domains=("b23.tv",),
        # vxbilibili 404s on b23 codes; vxb23.tv resolves them first.
        fix_domain="vxb23.tv",
        path_re=_compile(r"^/[\w-]{6,}/?$"),
    ),
    SiteRule(
        id="twitch",
        name="Twitch Clips",
        domains=("twitch.tv",),
        fix_domain="fxtwitch.seria.moe",
        path_re=_compile(r"/\w+/clip/[\w-]+|/videos/\d+"),
    ),
    SiteRule(
        id="twitch-clips",
        name="Twitch Clips (clips.twitch.tv)",
        domains=("clips.twitch.tv",),
        fix_domain="fxtwitch.seria.moe",
        path_re=_compile(r"^/[\w-]{6,}/?$"),
        # fxtwitch serves these at /clip/<slug>; the bare slug 404s.
        path_fn=lambda _host, path: f"/clip{path}",
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
