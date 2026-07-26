# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Instead, use GitHub's
[private vulnerability reporting](https://github.com/playfix/playfix/security/advisories/new), or
contact the maintainers directly. We'll acknowledge within a few days and keep you updated on a fix.

## Scope notes

- PlayFix requires a Discord **bot token** — treat it like a password. Keep it in `.env` (which is
  git-ignored) or your platform's secret store; never commit it.
- PlayFix requests **Manage Messages** and **Manage Webhooks**. It uses them only to delete the
  message it is reposting and to create/reuse a single webhook per channel named `PlayFix`.
- PlayFix does not store message content; only per-guild settings and webhook IDs.

## Supported versions

The latest release on `main` is supported.
