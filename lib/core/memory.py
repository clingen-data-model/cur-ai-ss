"""Handing freed heap back to the operating system.

A PDF parse allocates a few hundred megabytes of short-lived buffers: the
page renders for the table crops, the document with its embedded figure
images, the word layout. Python frees them when the parse ends, but glibc's
malloc keeps the pages in the process rather than returning them, so the
worker's resident memory stays where the parse left it. Measured on dev-caa
on 2026-11-09: a worker went from 477 MB to 1,074 MB across its first parse
and stayed there, 175 agent tasks after it adding 27 MB in all; in a fresh
process a parse added 300 MB, garbage collection returned none of it and
``malloc_trim(0)`` returned 200 MB. ``release_freed_memory`` is that call,
made after each parse. It is a no-op where there is no glibc (macOS, Windows,
musl), and it only ever returns memory nothing is using, so it is safe to
call at any time; it is not called after agent tasks because they free
nothing worth the walk of the heap.
"""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)


def _glibc_malloc_trim() -> ctypes.CDLL | None:
    if not sys.platform.startswith('linux'):
        return None
    try:
        libc = ctypes.CDLL('libc.so.6')
    except OSError:
        return None
    return libc if hasattr(libc, 'malloc_trim') else None


def release_freed_memory() -> bool:
    """Return the heap's free pages to the operating system. True when the
    call was made (glibc on Linux), False where there is nothing to call."""
    libc = _glibc_malloc_trim()
    if libc is None:
        return False
    libc.malloc_trim(0)
    return True
