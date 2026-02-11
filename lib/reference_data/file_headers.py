"""HTTP header-based caching for static reference files."""

from typing import Optional

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lib.models import StaticFileHeaderDB


def fetch_headers(url: str) -> dict[str, Optional[str]] | None:
    """Send an HTTP HEAD request and return relevant caching headers."""
    try:
        resp = requests.head(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    return {
        'etag': resp.headers.get('ETag'),
        'last_modified': resp.headers.get('Last-Modified'),
        'content_length': resp.headers.get('Content-Length'),
    }


def should_update_file(
    session: Session,
    file_identifier: str,
    url: str,
    model_class: type | None = None,
) -> bool:
    """Determine whether a reference file needs to be re-downloaded.

    Checks:
    1. If model_class is provided and the table is empty, always update.
    2. If no cached headers exist, always update.
    3. If remote headers match cached headers, skip update.
    """
    if model_class is not None:
        count = session.execute(select(func.count()).select_from(model_class)).scalar()
        if count == 0:
            return True

    cached = StaticFileHeaderDB.latest(session, file_identifier)
    if cached is None:
        return True

    remote_headers = fetch_headers(url)
    if remote_headers is None:
        return True

    return not cached.matches_headers(remote_headers)


def update_cached_headers(
    session: Session,
    file_identifier: str,
    url: str,
) -> None:
    """Fetch current headers and insert a new cache record."""
    remote_headers = fetch_headers(url)
    if remote_headers is None:
        return

    record = StaticFileHeaderDB(
        file_identifier=file_identifier,
        etag=remote_headers.get('etag'),
        last_modified=remote_headers.get('last_modified'),
        content_length=remote_headers.get('content_length'),
    )
    session.add(record)
    session.commit()
