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
- A fixer's "⚠️ Sensitive Content" / age-restricted card no longer counts as a working embed.
  The card is an embed like any other, so the spare-fixer retry never fired and the apology
  stayed on screen; PlayFix now reads it as a failure and retries the link on the spare.

[Unreleased]: https://github.com/playfix/playfix/commits/main
