"""Tarball format that carries a converted document between machines.

Members are named by their absolute path with the leading ``/`` dropped, because
``raw.json`` records its picture files by absolute path (see ``convert_result``)
and they must come back to exactly where they were written. ``unpack_tree``
refuses anything that would land outside the directory the caller expects.
"""

import os
import tarfile
from pathlib import Path


def pack_tree(root: Path, archive: Path) -> None:
    """Archive every file under ``root`` (an absolute path), keeping absolute names."""
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sorted(root.rglob('*')):
            tar.add(path, arcname=str(path.relative_to('/')), recursive=False)


def unpack_tree(archive: Path, root: Path) -> None:
    """Restore ``archive`` at the absolute paths it was packed from, under ``root`` only."""
    prefix = os.path.normpath(root) + os.sep
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        for member in members:
            target = os.path.normpath('/' + member.name)
            if not (member.isfile() or member.isdir()):
                raise ValueError(f'unsupported archive member {member.name!r}')
            if target != os.path.normpath(root) and not target.startswith(prefix):
                raise ValueError(f'archive member {member.name!r} is outside {root}')
        for member in members:
            target_path = Path('/' + member.name)
            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            assert source is not None
            with open(target_path, 'wb') as fp:
                fp.write(source.read())
