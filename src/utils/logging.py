"""Logging setup using Loguru."""

import sys
from loguru import logger

from src.config import settings


def setup_logging() -> None:
    """
    Configure Loguru logger for Afterburner.
    
    Uses VERBOSE setting to control log level:
    - VERBOSE=True  → DEBUG level
    - VERBOSE=False → INFO level
    """
    logger.remove()  # Remove default handler

    log_level = "DEBUG" if settings.VERBOSE else "INFO"

    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    logger.debug("Afterburner logging initialised (level={})", log_level)
