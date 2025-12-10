"""Base types for the evagg library."""

from .base import HGVSVariant, Paper
from .prompt_tag import PromptTag

__all__ = [
    # Base.
    'Paper',
    'HGVSVariant',
    'PromptTag',
]
