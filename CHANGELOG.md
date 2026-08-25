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

[Unreleased]: https://github.com/playfix/playfix/commits/main
