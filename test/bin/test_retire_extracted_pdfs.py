"""The one-off move of extracted_pdfs/ leftovers into documents/."""

from pathlib import Path

from lib.bin.retire_extracted_pdfs import retire_paper
from lib.misc.pdf.paths import (
    document_raw_path,
    document_thumbnail_path,
    snapshots_dir,
)


def _legacy(root: Path, paper_id: int) -> Path:
    legacy = root / 'extracted_pdfs' / str(paper_id)
    legacy.mkdir(parents=True)
    return legacy


def test_moves_thumbnail_and_snapshots_and_copies_a_missing_raw(mocked_root_dir):
    root = Path(mocked_root_dir)
    legacy = _legacy(root, 5)
    (legacy / 'thumbnail.png').write_bytes(b'thumb')
    (legacy / 'snapshots').mkdir()
    (legacy / 'snapshots' / 'extraction_1.json').write_text('{}')
    (legacy / 'raw.pdf').write_bytes(b'pdf')
    (legacy / 'supplements').mkdir()
    (legacy / 'supplements' / 'raw.docx').write_bytes(b'docx')
    (legacy / 'raw.json').write_text('{}')  # dead, stays behind

    actions = retire_paper(5, legacy, dry_run=False)

    assert document_thumbnail_path(5).read_bytes() == b'thumb'
    assert (snapshots_dir(5) / 'extraction_1.json').exists()
    assert document_raw_path(5).read_bytes() == b'pdf'
    assert document_raw_path(5, supplement=True, file_format='docx').exists()
    assert not (legacy / 'thumbnail.png').exists()
    assert not (legacy / 'snapshots').exists()
    assert (legacy / 'raw.json').exists()
    assert len(actions) == 4
    # Idempotent: a second run finds nothing to move.
    assert retire_paper(5, legacy, dry_run=False) == []


def test_leaves_a_file_already_in_documents_alone(mocked_root_dir):
    root = Path(mocked_root_dir)
    legacy = _legacy(root, 6)
    (legacy / 'thumbnail.png').write_bytes(b'old')
    document_thumbnail_path(6).parent.mkdir(parents=True)
    document_thumbnail_path(6).write_bytes(b'new')
    (legacy / 'raw.pdf').write_bytes(b'pdf')
    document_raw_path(6).parent.mkdir(parents=True)
    document_raw_path(6).write_bytes(b'pdf-already')

    actions = retire_paper(6, legacy, dry_run=False)

    assert document_thumbnail_path(6).read_bytes() == b'new'
    assert document_raw_path(6).read_bytes() == b'pdf-already'
    assert (legacy / 'thumbnail.png').exists()
    assert actions == ['thumbnail.png: already in documents/, legacy copy left']


def test_dry_run_writes_nothing(mocked_root_dir):
    root = Path(mocked_root_dir)
    legacy = _legacy(root, 7)
    (legacy / 'thumbnail.png').write_bytes(b'thumb')

    actions = retire_paper(7, legacy, dry_run=True)

    assert actions == ['thumbnail.png: moved']
    assert (legacy / 'thumbnail.png').exists()
    assert not document_thumbnail_path(7).exists()
