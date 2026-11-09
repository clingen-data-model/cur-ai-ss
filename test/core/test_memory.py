"""release_freed_memory hands glibc's free pages back after a parse, and is a
no-op everywhere glibc is not."""

import ctypes
import sys

from lib.core import memory


class _FakeLibc:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def malloc_trim(self, pad: int) -> int:
        self.calls.append(pad)
        return 1


def test_on_linux_with_glibc_it_trims_the_whole_heap(monkeypatch):
    libc = _FakeLibc()
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(ctypes, 'CDLL', lambda name: libc)

    assert memory.release_freed_memory() is True
    assert libc.calls == [0]


def test_off_linux_it_does_nothing(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')

    def no_load(name: str) -> None:
        raise AssertionError('must not try to load libc off Linux')

    monkeypatch.setattr(ctypes, 'CDLL', no_load)

    assert memory.release_freed_memory() is False


def test_a_linux_without_glibc_is_a_no_op(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')

    def missing(name: str) -> None:
        raise OSError('libc.so.6: cannot open shared object file')

    monkeypatch.setattr(ctypes, 'CDLL', missing)

    assert memory.release_freed_memory() is False


def test_a_libc_without_malloc_trim_is_a_no_op(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(ctypes, 'CDLL', lambda name: object())

    assert memory.release_freed_memory() is False
