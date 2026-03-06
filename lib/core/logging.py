import logging
import sys

from lib.core.environment import env


def setup_logging() -> None:
    logging.basicConfig(
        level=env.LOG_LEVEL.value,
        format='%(asctime)s [%(levelname)s] [%(process)d] %(name)s: %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
