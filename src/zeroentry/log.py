"""Logging setup. Secrets never reach the log: URLs are masked, request bodies are never logged."""

import logging

from sqlalchemy.engine import make_url

LOGGER_NAME = "zeroentry"


def configure_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    return logging.getLogger(LOGGER_NAME)


def mask_url(url: str) -> str:
    """Render a database URL with the password replaced by ***."""
    return make_url(url).render_as_string(hide_password=True)
