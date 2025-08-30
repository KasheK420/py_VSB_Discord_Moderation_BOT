"""
bot/utils/logging_config.py
Logging configuration
"""

import logging
import sys


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log")],
    )

    # Set specific loggers
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
