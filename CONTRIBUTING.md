# Contributing to PlayFix

Thanks for helping! Most contributions are small and welcome — especially adding or fixing platforms.

## Dev setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make check          # ruff + pytest
```

## Adding or fixing a platform

Nearly every platform is **one entry** in [`src/playfix/sites.py`](src/playfix/sites.py):

```python
# one more entry in the SITES tuple in src/playfix/sites.py
SiteRule(
    id="example",
    name="Example",
    domains=("example.com",),  # source domains (subdomains match automatically)
    fix_domain="fxexample.com",  # the embed-fixer domain
    path_re=_c(r"/post/\d+"),  # only rewrite real content URLs, not profiles/home
)
```

Then add a couple of cases to [`tests/test_rewrite.py`](tests/test_rewrite.py) — one URL that should be
fixed, and one (a profile or the site root) that should **not** be. Run `make check`.

Guidelines:
- Only rewrite **content** URLs (a post/video/reel), never profile or home pages — keep `path_re` tight.
- Prefer well-established fixer domains. Avoid ones that clearly run on throwaway/dynamic-DNS hosts.
- Keep it a pure data/regex change when you can; that's what makes PlayFix easy to maintain.

## Branches & commits

- Branch off `dev` (`feat/…` or `fix/…`); PRs target `dev`.
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`.
- CI (ruff + pytest) must pass. Please don't add `.github/workflows/` — CI runs on Woodpecker via
  [`.woodpecker.yml`](.woodpecker.yml).

## Scope

PlayFix stays small: fix links, repost nicely, per-guild config. Big new subsystems are unlikely to be
merged — open an issue to discuss first.
