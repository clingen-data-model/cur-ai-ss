"""Parse PDFs through the PDF parsing service into a throwaway CAA_ROOT, wipe it.

A rehearsal of the worker's PDF Parsing step with the converter on Cloud Run
(``lib.misc.pdf.remote``): each PDF is written as a paper's raw.pdf under a
temporary CAA_ROOT, sent to the service, and the parse finishes locally as it
would in the worker -- tables/ and images/, words.json, anchored.md and
anchors.json -- so what comes back can be judged by the same files the
agents read. The temporary root is deleted at the end unless ``--keep``.

    uv run python -m lib.bin.parse_remote_test paper.pdf [more.pdf ...] \\
        --url https://pdf-parsing-<hash>.run.app

``--url`` defaults to PDF_PARSING_SERVICE_URL. ``--compare-local`` parses each PDF
with the in-process converter as well and prints both side by side (minutes
per paper on a laptop). Table correction, the vision-model step, is skipped
unless ``--correct-tables``, so the rehearsal costs no model calls by default.
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('pdfs', nargs='+', type=Path, help='PDF files to parse')
    parser.add_argument(
        '--url',
        default=os.environ.get('PDF_PARSING_SERVICE_URL'),
        help='service base URL (default: $PDF_PARSING_SERVICE_URL)',
    )
    parser.add_argument(
        '--compare-local',
        action='store_true',
        help='also parse with the in-process converter and print both',
    )
    parser.add_argument(
        '--correct-tables',
        action='store_true',
        help='run the vision table-correction step too (model calls)',
    )
    parser.add_argument(
        '--keep', action='store_true', help='leave the temporary CAA_ROOT in place'
    )
    args = parser.parse_args(argv)
    if not args.url:
        parser.error('--url or PDF_PARSING_SERVICE_URL is required')
    return args


def _count(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def describe(document: Any, paper_id: int) -> dict[str, Any]:
    """What a parse left behind, by the numbers."""
    from lib.misc.pdf.paths import (
        document_anchored_md_path,
        document_anchors_path,
        document_images_dir,
        document_tables_dir,
        document_words_json_path,
    )

    anchored = document_anchored_md_path(paper_id).read_text()
    return {
        'pages': len(document.pages),
        'texts': len(document.texts),
        'tables': len(document.tables),
        'pictures': len(document.pictures),
        'table pngs': _count(document_tables_dir(paper_id), '*.png'),
        'table md': _count(document_tables_dir(paper_id), '*.md'),
        'figure pngs': _count(document_images_dir(paper_id), '*.png'),
        'words': len(json.loads(document_words_json_path(paper_id).read_text())),
        'anchors': len(json.loads(document_anchors_path(paper_id).read_text())),
        'anchored.md lines': anchored.count('\n'),
        'anchored.md chars': len(anchored),
    }


async def run_one(
    pdf: Path, paper_id: int, *, url: str | None, correct: bool
) -> tuple[dict[str, Any], float]:
    """Parse one PDF as paper ``paper_id``: remotely at ``url``, or locally
    when ``url`` is None. Returns the description and the converter's seconds."""
    from lib.misc.pdf.parse import convert_locally, write_parse_outputs
    from lib.misc.pdf.paths import document_raw_path
    from lib.misc.pdf.remote import convert_pdf_remote

    content = pdf.read_bytes()
    raw = document_raw_path(paper_id)
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(content)

    started = time.monotonic()
    if url:
        document = await convert_pdf_remote(content, base_url=url)
    else:
        document = convert_locally(content)
    elapsed = time.monotonic() - started

    await write_parse_outputs(document, content, paper_id, correct=correct)
    return describe(document, paper_id), elapsed


def print_report(pdf: Path, results: dict[str, tuple[dict[str, Any], float]]) -> None:
    sources = list(results)
    print(f'\n== {pdf.name}')
    width = max(len(k) for k in next(iter(results.values()))[0]) + 2
    print(' ' * width + ''.join(f'{s:>12}' for s in sources))
    print(
        f'{"convert s":<{width}}' + ''.join(f'{results[s][1]:>12.1f}' for s in sources)
    )
    for key in next(iter(results.values()))[0]:
        print(f'{key:<{width}}' + ''.join(f'{results[s][0][key]:>12}' for s in sources))


async def main_async(args: argparse.Namespace) -> None:
    for i, pdf in enumerate(args.pdfs):
        results: dict[str, tuple[dict[str, Any], float]] = {}
        results['remote'] = await run_one(
            pdf, 2 * i + 1, url=args.url, correct=args.correct_tables
        )
        if args.compare_local:
            results['local'] = await run_one(
                pdf, 2 * i + 2, url=None, correct=args.correct_tables
            )
        print_report(pdf, results)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    for pdf in args.pdfs:
        if not pdf.is_file():
            sys.exit(f'not a file: {pdf}')

    # Settings are read when lib is first imported, so the throwaway root has
    # to be in the environment before then; the rest of .env still applies.
    root = tempfile.mkdtemp(prefix='caa-parse-rehearsal-')
    os.environ['CAA_ROOT'] = root
    logging.basicConfig(
        level=logging.INFO, format='%(levelname)s %(name)s: %(message)s'
    )
    try:
        asyncio.run(main_async(args))
    finally:
        if args.keep:
            print(f'\nkept: {root}')
        else:
            shutil.rmtree(root, ignore_errors=True)
            print(f'\nwiped: {root}')


if __name__ == '__main__':
    main()
