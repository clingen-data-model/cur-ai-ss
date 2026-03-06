import logging
import sys

from lib.core.environment import env


def setup_logging(name: str) -> logging.Logger:
    """
    Configure logging to stdout with shared format.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(env.LOG_LEVEL.value)
    logger.handlers.clear()
    logger.propagate = False  # Don't propagate to root logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(process)d] %(name)s: %(message)s'
        )
    )
    logger.addHandler(handler)

    return logger
