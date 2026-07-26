<div align="center">

# 🎬 PlayFix

**Make social media links play in Discord — reposted as you.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Built with discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2.svg)](https://github.com/Rapptz/discord.py)

</div>

Discord stopped reliably embedding videos from X/Twitter, TikTok, Instagram, Reddit and friends.
**PlayFix** watches for those links, rewrites them to a working embed-fixer domain so the video
actually plays, and — if you want — **reposts the message as the original author** (their name and
avatar) so the fix looks seamless.

One bot covers every server you add it to.

---

## ✨ Features

- **Plays everywhere it should** — X/Twitter, TikTok, Instagram, Reddit, Bluesky, Tumblr, Pixiv,
  Facebook, BiliBili, Twitch clips, Mastodon, and more. Adding a platform is [one line](CONTRIBUTING.md).
- **Post as you** — reposts via webhook under the author's name + avatar, then removes the broken
  original. Or run in safe **reply** mode instead (see below).
- **Per-server config** — `/playfix` slash commands, admin-only. Sensible defaults, zero setup to start.
- **Multi-server** — one instance serves all your guilds.
- **Small & self-hostable** — a single Python process, SQLite, no external database. `docker compose up`.
- **Well-behaved** — never re-pings anyone, ignores bots/itself, and falls back gracefully when it
  lacks permissions.

## 🚀 Quick start (self-host)

```bash
git clone https://github.com/playfix/playfix
cd playfix
cp .env.example .env      # then paste your bot token into .env
docker compose up -d
```

That's it. Now invite it and configure it (below).

<details>
<summary>Run without Docker</summary>

```bash
pip install .
PLAYFIX_TOKEN=your-token python -m playfix
```
</details>

## 🔗 Invite it to a server

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications) →
   **Bot** → **Reset Token** (put it in `.env`).
2. On the **Bot** page, enable **Message Content Intent** (under *Privileged Gateway Intents*).
3. Invite it (replace `YOUR_APP_ID`):

   ```
   https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&permissions=275414871040&scope=bot+applications.commands
   ```

   That permission set is: View Channels, Send Messages, Send Messages in Threads, Embed Links, Read
   Message History, **Manage Messages** (to delete the original) and **Manage Webhooks** (to post as you).
   You need *Manage Server* on a guild to add it there.

## ⚙️ Configuration

Admins configure PlayFix per server with `/playfix`:

| Command | What it does |
|---|---|
| `/playfix status` | Show current settings |
| `/playfix enable` · `disable` | Turn PlayFix on/off in this server |
| `/playfix mode webhook\|reply` | How fixed links are posted (see below) |
| `/playfix delete-original <true\|false>` | Whether webhook mode deletes the original |
| `/playfix channel <true\|false>` | Enable/disable PlayFix in the current channel |

Process-level options live in `.env` — see [`.env.example`](.env.example).

## 🎭 `webhook` vs `reply` mode

- **`webhook` (default):** deletes the original message and reposts it via a channel webhook using the
  author's name and avatar, with the link fixed. Looks like the author posted the working version.
  Needs **Manage Messages** + **Manage Webhooks**.
- **`reply`:** leaves the original, suppresses its broken preview, and replies with the fixed link.
  Non-destructive — a good choice if you'd rather PlayFix not delete messages.

If PlayFix lacks the permissions for `webhook` mode in a channel, it automatically falls back to `reply`.

## ❓ FAQ

**Why does the reposted message have an `APP` tag next to my name?**
Discord adds an `APP` badge to *every* webhook and bot message — it can't be removed by any legitimate
means. So "post as you" gets your name and avatar, but the small `APP` tag stays. (The only way around
it is a user-token selfbot, which is against Discord's ToS — PlayFix will never do that.)

**Does it store my messages?**
No. PlayFix only stores per-server settings and the IDs of webhooks it creates. Message content is
never logged.

**Something isn't fixing / a fixer site is down.**
The fixer services are community-run and occasionally have outages. Open an issue and we'll adjust the
mapping in [`sites.py`](src/playfix/sites.py).

## 🛠️ How it works

`on_message` → [`rewrite.py`](src/playfix/rewrite.py) extracts URLs and matches them against the
[`sites.py`](src/playfix/sites.py) rules table (source domains + a content-path pattern → fixer domain)
→ [`repost.py`](src/playfix/repost.py) posts the result as the author (webhook) or as a reply.

## 🤝 Contributing

Adding or fixing a platform is usually **one entry** in `sites.py`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## 🙏 Credits

- Domain mappings adapted (data only) from [FixTweetBot](https://github.com/Kyrela/FixTweetBot) — see [NOTICE](NOTICE).
- The embed magic is done by community fixer services: [FxEmbed](https://github.com/FxEmbed/FxEmbed) and others.

## 📄 License

[MIT](LICENSE). PlayFix is an independent project and is not affiliated with Discord Inc.
