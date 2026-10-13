"""Move one file to or from a ``gs://`` object or a ``file://`` path.

``file://`` exists so the service can be run and tested without GCP.
"""

import shutil
from pathlib import Path
from urllib.parse import urlparse


def _split_gs(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip('/')


def download(uri: str, dest: Path) -> None:
    if uri.startswith('gs://'):
        from google.cloud import storage

        bucket, name = _split_gs(uri)
        storage.Client().bucket(bucket).blob(name).download_to_filename(str(dest))
    elif uri.startswith('file://'):
        shutil.copyfile(urlparse(uri).path, dest)
    else:
        raise ValueError(f'unsupported storage uri {uri!r}')


def upload(src: Path, uri: str) -> None:
    if uri.startswith('gs://'):
        from google.cloud import storage

        bucket, name = _split_gs(uri)
        storage.Client().bucket(bucket).blob(name).upload_from_filename(str(src))
    elif uri.startswith('file://'):
        dest = Path(urlparse(uri).path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    else:
        raise ValueError(f'unsupported storage uri {uri!r}')
