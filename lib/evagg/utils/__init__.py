"""Package for utilities."""

from .logging import init_logger
from .web import RequestsWebContentClient

__all__ = [
    # Logging.
    "init_logger",
    # Web.
    "RequestsWebContentClient",
]
