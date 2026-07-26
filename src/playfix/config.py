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
