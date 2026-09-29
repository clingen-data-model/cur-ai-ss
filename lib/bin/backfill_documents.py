#!/usr/bin/env python3
"""Build the anchor-indexed document folder for papers parsed before it existed.

TEMPORARY: delete this script when extracted_pdfs/ is retired.

For every ``extracted_pdfs/{id}`` that finished parsing, derives
``documents/{id}/{main,supplement}`` (anchored.md, anchors.json, tables/,
images/) from the Docling ``raw.json`` already on disk -- no Docling re-run,
no model calls; existing vision corrections are re-keyed and reused. Goes
through the same ``write_anchored_document`` the live parse uses, so the two
paths produce identical output. Reads the old folder, never writes to it.

Idempotent: a paper whose new ``_SUCCESS`` marker exists is skipped unless
``--force``.

Usage:
    uv run python -m lib.bin.backfill_documents [--paper-id N] [--force]
"""

import argparse
import logging
import re
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.anchors import load_anchors
from lib.misc.pdf.parse import write_anchored_document, write_anchored_xlsx
from lib.misc.pdf.paths import (
    document_anchored_md_path,
    document_success_path,
    document_table_vision_markdown_path,
    document_tables_dir,
    pdf_extraction_success_path,
    pdf_json_path,
    pdf_markdown_path,
    pdf_raw_path,
    pdf_supplements_dir,
)
from lib.models.paper import FileFormat

setup_logging()
logger = logging.getLogger(__name__)


def _supplement_format(paper_id: int) -> FileFormat | None:
    for fmt in FileFormat:
        if pdf_raw_path(paper_id, supplement=True, file_format=fmt.value).exists():
            return fmt
    return None


def _summarize(paper_id: int, supplement: bool) -> str:
    anchors = load_anchors(paper_id, supplement)
    tables = [a for a in anchors if re.match(r'^(supp-)?table-', a.id)]
    with_rows = [t for t in tables if any(t.row_boxes)]
    vision = [
        t
        for t in tables
        if document_table_vision_markdown_path(
            paper_id, int(t.id.rsplit('-', 1)[1]), supplement
        ).exists()
    ]
    figures = sum(1 for a in anchors if re.match(r'^(supp-)?figure-', a.id))
    warnings = (
        document_anchored_md_path(paper_id, supplement)
        .read_text()
        .count('EXTRACTION WARNING')
    )
    return (
        f'{len(anchors)} anchors, {len(tables)} tables '
        f'({len(with_rows)} with row boxes, {len(vision)} vision-corrected, '
        f'{warnings} unrecovered), {figures} figures'
    )


def backfill_paper(paper_id: int, force: bool = False) -> list[str]:
    """Build main + supplement for one paper; returns one summary line per document."""
    lines = []
    docs: list[tuple[bool, FileFormat | None]] = [(False, None)]
    if pdf_supplements_dir(paper_id).exists():
        if (fmt := _supplement_format(paper_id)) is not None:
            docs.append((True, fmt))

    for supplement, fmt in docs:
        label = 'supplement' if supplement else 'main'
        if not pdf_extraction_success_path(paper_id, supplement=supplement).exists():
            lines.append(f'{label}: old parse incomplete, skipped')
            continue
        if document_success_path(paper_id, supplement).exists() and not force:
            lines.append(f'{label}: already built, skipped')
            continue

        if fmt == FileFormat.XLSX:
            write_anchored_xlsx(
                paper_id, pdf_markdown_path(paper_id, supplement=True).read_text()
            )
        else:
            json_path = pdf_json_path(paper_id, supplement=supplement)
            if not json_path.exists():
                lines.append(f'{label}: no raw.json, skipped')
                continue
            document = DoclingDocument.load_from_json(json_path)
            write_anchored_document(
                document,
                paper_id,
                supplement=supplement,
                file_format=fmt.value if fmt else None,
            )
        lines.append(f'{label}: {_summarize(paper_id, supplement)}')
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper-id', type=int, help='Only this paper')
    parser.add_argument('--force', action='store_true', help='Rebuild even if built')
    args = parser.parse_args()

    if args.paper_id is not None:
        paper_ids = [args.paper_id]
    else:
        paper_ids = sorted(
            int(p.name)
            for p in Path(env.extracted_pdf_dir).iterdir()
            if p.name.isdigit()
        )

    built = failed = 0
    for paper_id in paper_ids:
        try:
            for line in backfill_paper(paper_id, force=args.force):
                logger.info(f'paper {paper_id} {line}')
            built += 1
        except Exception:
            failed += 1
            logger.exception(f'paper {paper_id} failed')

    logger.info(f'done: {built} papers processed, {failed} failed')
    if not document_tables_dir(paper_ids[0]).exists() and paper_ids:
        logger.warning('no tables dir written for the first paper; check CAA_ROOT')


if __name__ == '__main__':
    main()
