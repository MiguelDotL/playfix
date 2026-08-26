"""Pure link-rewriting logic — no Discord, no I/O, fully unit-testable.

``rewrite_text`` is the single entry point the bot uses: give it message content,
get back the content with every supported social link swapped to its fixer domain,
plus a record of what changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from .sites import SITES, SiteRule

# Build an exact domain -> rule index once. Subdomains are handled by walking the
# host from most- to least-specific (see ``_match``), so "www."/"m."/"vm." etc.
# resolve to the registrable domain without being enumerated.
_INDEX: dict[str, SiteRule] = {domain: rule for rule in SITES for domain in rule.domains}

# Grab http(s) URLs; stop at whitespace, quotes, angle brackets and closing
# brackets/parens so markdown links and <suppressed> links extract cleanly.
_URL_RE = re.compile(r"https?://[^\s<>\"'`\]})]+", re.IGNORECASE)

# Trailing characters that are almost always punctuation, not part of the URL.
_TRAILING = ".,!?;:'\"`*_~"


@dataclass(frozen=True, slots=True)
class RewriteResult:
    """Outcome of rewriting a block of text."""

    text: str
    #: ``(original_url, fixed_url)`` for every link that was changed.
    rewrites: list[tuple[str, str]]
    #: ``fixed_url -> same link on the rule's fallback fixer``, for the subset of
    #: rewrites whose rule declares a spare. Used to retry a link that drew no embed.
    fallbacks: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.rewrites)

    def fallback_text(self) -> str:
        """``text`` with every fallback-capable link swapped to its spare fixer."""
        out = self.text
        for fixed, spare in self.fallbacks.items():
            out = out.replace(fixed, spare)
        return out


def _match(host: str) -> SiteRule | None:
    """Resolve a hostname to a rule, honouring subdomains (longest suffix wins)."""
    labels = host.split(".")
    for i in range(len(labels) - 1):  # stop before a bare TLD
        rule = _INDEX.get(".".join(labels[i:]))
        if rule is not None:
            return rule
    return None


def _rewrite(url: str) -> tuple[str, str | None] | None:
    """Return ``(fixed_url, fallback_url_or_None)``, or ``None`` if no rule applies."""
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        return None
    rule = _match(host)
    if rule is None:
        return None
    path_and_query = parts.path + (f"?{parts.query}" if parts.query else "")
    if not rule.path_re.search(path_and_query):
        return None

    # Replace the whole netloc (drops any userinfo/port); keep path/fragment, and
    # keep the query unless the rule says it is tracking-only noise.
    query = "" if rule.strip_query else parts.query

    def swap(domain: str) -> str:
        return urlunsplit(parts._replace(netloc=domain, query=query))

    spare = swap(rule.fallback_domain) if rule.fallback_domain else None
    return swap(rule.fix_domain), spare


def rewrite_url(url: str) -> str | None:
    """Rewrite a single URL to its fixer domain, or ``None`` if it doesn't apply."""
    result = _rewrite(url)
    return result[0] if result is not None else None


def _find_urls(text: str) -> list[tuple[int, int, str]]:
    """Return ``(start, end, url)`` spans with trailing punctuation trimmed off."""
    spans: list[tuple[int, int, str]] = []
    for m in _URL_RE.finditer(text):
        start, end = m.start(), m.end()
        url = m.group()
        while url and url[-1] in _TRAILING:
            url = url[:-1]
            end -= 1
        if url:
            spans.append((start, end, url))
    return spans


def rewrite_text(text: str) -> RewriteResult:
    """Swap every supported social link in ``text`` for its fixer version."""
    rewrites: list[tuple[str, str]] = []
    fallbacks: dict[str, str] = {}
    out: list[str] = []
    cursor = 0
    for start, end, url in _find_urls(text):
        result = _rewrite(url)
        if result is None:
            continue
        fixed, spare = result
        if fixed == url:
            continue
        out.append(text[cursor:start])
        out.append(fixed)
        cursor = end
        rewrites.append((url, fixed))
        if spare is not None and spare != fixed:
            fallbacks[fixed] = spare
    out.append(text[cursor:])
    return RewriteResult("".join(out), rewrites, fallbacks)
