"""Entry point: ``python -m playfix``."""

from __future__ import annotations

import logging
import sys

from pydantic import ValidationError

from .bot import PlayFix
from .config import Settings


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        sys.exit(
            "PlayFix: no bot token found. Set PLAYFIX_TOKEN (or DISCORD_TOKEN), "
            "e.g. in a .env file. See .env.example."
        )

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = PlayFix(settings)
    bot.run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
