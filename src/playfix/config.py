"""Runtime configuration, loaded from the environment (12-factor)."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["webhook", "reply"]


class Settings(BaseSettings):
    """Process-wide settings. Everything but the token has a sane default."""

    model_config = SettingsConfigDict(env_prefix="PLAYFIX_", env_file=".env", extra="ignore")

    #: Bot token. Accepts PLAYFIX_TOKEN or the conventional DISCORD_TOKEN.
    token: str = Field(..., validation_alias=AliasChoices("PLAYFIX_TOKEN", "DISCORD_TOKEN"))

    db_path: str = "data/playfix.sqlite3"
    log_level: str = "INFO"

    #: Default per-guild behaviour (overridable at runtime via /playfix).
    default_mode: Mode = "webhook"
    default_delete_original: bool = True

    #: Best-effort attachment re-upload cap (MB) when reposting as the author.
    max_attachment_mb: int = 8
    #: Discord hard limit on a single message's content length.
    max_content_length: int = 2000

    #: Seconds to wait before checking whether Discord attached an embed to a repost.
    #: Discord crawls the link after the message lands, so the check has to be late
    #: enough to avoid a false negative and early enough that nobody has scrolled past.
    embed_check_delay: float = 4.0
    #: How many times to look before giving up on the primary fixer. A slow-but-fine
    #: crawl would otherwise cost us the primary's better click-through for nothing.
    embed_check_attempts: int = 2
    #: Retry a link on its fixer's ``fallback_domain`` when no embed showed up.
    embed_fallback: bool = True
