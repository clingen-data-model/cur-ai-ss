#!/usr/bin/env python3
"""Move what the pipeline still reads out of extracted_pdfs/ into documents/.

ONE-OFF: run once per deployment when the documents-only layout ships, then
delete this script.

The parser, the API and the snapshot store now read and write only
``documents/{id}/`` (lib/misc/pdf/paths.py). Papers parsed before that have
their uploaded files and parse output under ``documents/`` already (the
parser copied them there since the anchored layout shipped), but two things
lived only in the old folder:

- ``extracted_pdfs/{id}/thumbnail.png`` -> ``documents/{id}/thumbnail.png``
- ``extracted_pdfs/{id}/snapshots/``   -> ``documents/{id}/snapshots/``

This script moves those, copies a ``raw.*`` across for any paper whose
``documents/`` copy is missing, and reports per paper. Nothing in
``extracted_pdfs/`` is deleted: once the report is clean, remove the folder by
hand (``rm -rf {CAA_ROOT}/extracted_pdfs``).

Idempotent: a file already in place is left alone, and a second run reports
nothing to do.

Usage:
    uv run python -m lib.bin.retire_extracted_pdfs [--dry-run]
"""

import argparse
import logging
import shutil
from pathlib import Path

from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.paths import (
    document_paper_dir,
    document_raw_path,
    document_thumbnail_path,
    snapshots_dir,
)
from lib.models.paper import FileFormat

setup_logging()
logger = logging.getLogger(__name__)

LEGACY_DIR = Path(env.CAA_ROOT) / 'extracted_pdfs'


def _move(src: Path, dest: Path, dry_run: bool) -> str | None:
    """Move src to dest unless dest exists; what happened, or None if nothing to do."""
    if not src.exists():
        return None
    if dest.exists():
        return f'{dest.name}: already in documents/, legacy copy left'
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    return f'{dest.name}: moved'


def _copy_raw_if_missing(
    paper_id: int, legacy: Path, *, supplement: bool, dry_run: bool
) -> str | None:
    """A paper whose documents/ copy of the upload never got written."""
    legacy_base = legacy / 'supplements' if supplement else legacy
    for fmt in (None, *[f.value for f in FileFormat]):
        src = legacy_base / f'raw.{fmt or "pdf"}'
        if not src.exists():
            continue
        dest = document_raw_path(paper_id, supplement=supplement, file_format=fmt)
        if dest.exists():
            return None
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return f'{"supplement" if supplement else "main"} {src.name}: copied'
    return None


def retire_paper(paper_id: int, legacy: Path, dry_run: bool) -> list[str]:
    actions = [
        _move(legacy / 'thumbnail.png', document_thumbnail_path(paper_id), dry_run),
        _move(legacy / 'snapshots', snapshots_dir(paper_id), dry_run),
        _copy_raw_if_missing(paper_id, legacy, supplement=False, dry_run=dry_run),
        _copy_raw_if_missing(paper_id, legacy, supplement=True, dry_run=dry_run),
    ]
    return [a for a in actions if a]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='report only')
    args = parser.parse_args()

    if not LEGACY_DIR.exists():
        logger.info(f'{LEGACY_DIR} does not exist; nothing to do')
        return

    papers = sorted((int(p.name), p) for p in LEGACY_DIR.iterdir() if p.name.isdigit())
    touched = 0
    for paper_id, legacy in papers:
        actions = retire_paper(paper_id, legacy, args.dry_run)
        if actions:
            touched += 1
            logger.info(f'paper {paper_id}: ' + '; '.join(actions))
        if not document_paper_dir(paper_id).exists():
            logger.warning(f'paper {paper_id}: no documents/ folder at all')
    logger.info(
        f'{len(papers)} legacy paper folders, {touched} with something to move'
        + (' (dry run, nothing written)' if args.dry_run else '')
        + f'. When the report is clean: rm -rf {LEGACY_DIR}'
    )


if __name__ == '__main__':
    main()
