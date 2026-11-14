# Changelog

All notable changes to PlayFix are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Initial release.
- Link rewriting for ~15 platforms (X/Twitter, Instagram, TikTok, Reddit, Bluesky, Tumblr, Pixiv,
  DeviantArt, Newgrounds, Facebook, BiliBili, Twitch clips, Spotify, Fur Affinity, Mastodon).
- `webhook` mode (repost as the author + delete original) and non-destructive `reply` mode, with
  automatic fallback when permissions are missing.
- Per-guild configuration via `/playfix` slash commands, stored in SQLite.
- Docker image + `docker-compose.yml` for one-command self-hosting.
- Per-site `strip_query` rule flag, enabled for Instagram: the `?igsh=` share tracker is
  dropped from the fixed link instead of being carried into the repost.
- Per-site `fallback_domain`: when a repost draws no embed, the link is retried on that site's
  spare fixer (TikTok `tnktok.com` → `tiktokez.com`). Tunable via `PLAYFIX_EMBED_FALLBACK`,
  `PLAYFIX_EMBED_CHECK_DELAY` and `PLAYFIX_EMBED_CHECK_ATTEMPTS`.

### Fixed
- TikTok's spare fixer is now `kktiktok.com`. `tiktokez.com` had started sending crawlers to an
  EmbedEZ download page with no preview tags, so every retry failed; `kktiktok.com` serves the video
  even for age-restricted TikToks.
- Links wrapped in `<angle brackets>` or inside code are no longer rewritten. The author asked for no
  preview, so the repost changed nothing except the author's message.
- Replies are fixed in reply mode instead of being reposted. A webhook can't reply, so the repost
  lost the link to the message it answered.
- A message whose attachment is too large to re-upload, or fails to download, is no longer deleted.
  The attachment used to be dropped silently and lost with the original.
- A webhook deleted from under PlayFix is recreated. The stale cached copy used to push every later
  message in that channel into reply mode until a restart.
- Instagram links now rewrite to `vxinstagram.com`, with `kkinstagram.com` demoted to the spare.
  `kkinstagram.com` returned some reels as their cover image instead of the video, so the
  repost showed a still picture; `vxinstagram.com` served the playable mp4 for the same reel.
- Facebook links now rewrite to `facebed.seria.moe`, with `facebed.com` demoted to the spare.
  Both run the same facebed software and serve byte-comparable OpenGraph tags, yet `facebed.com`
  drew no embed in Discord where `facebed.seria.moe` played the video on the same link.
- A fixer's "⚠️ Sensitive Content" / age-restricted card no longer counts as a working embed.
  The card is an embed like any other, so the spare-fixer retry never fired and the apology
  stayed on screen; PlayFix now reads it as a failure and retries the link on the spare.
- The primary fixer's link is restored when the spare draws nothing either. Spares go down
  too — `tiktokez.com` answers "Failed to Get Post" for age-restricted TikToks — and a bare
  link to a second dead fixer tells the reader less than the first one's "age-restricted" card.

[Unreleased]: https://github.com/playfix/playfix/commits/main
