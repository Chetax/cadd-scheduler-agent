import logging
import sys
from backend.core.config import settings


def setup_logging() -> None:
    """Call once at app startup — configures the root logger for the whole app."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)

    # avoid duplicate handlers if called more than once
    if not root.handlers:
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Use this in every module instead of logging.getLogger directly."""
    return logging.getLogger(name)