import logging
import logging.handlers
import sys

# Handlers
log_handler = logging.handlers.TimedRotatingFileHandler(
    filename="discord.log", encoding="utf-8", when="midnight", backupCount=10
)

stream_handler = logging.StreamHandler(sys.stdout)

# Formatter
dt_fmt = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter("[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{")

log_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)


# Logger setup
def get_logger(name: str):
    """
    Configures and returns a logger with a given name.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Add handlers to logger
    logger.addHandler(log_handler)
    logger.addHandler(stream_handler)

    return logger
