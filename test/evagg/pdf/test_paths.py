"""What the agents are handed to read: the anchored documents, headed."""

import pytest

from lib.misc.pdf.anchors import paper_block_texts
from lib.misc.pdf.paths import (
    SUPPLEMENTARY_MATERIAL_HEADER,
    document_anchored_md_path,
    fulltext_md,
)
from lib.models.paper import FileFormat

MAIN = (
    '## Abstract\n\n'
    '[paragraph-1] We report a family.\n\n'
    '## Methods\n\n'
    '[paragraph-2] Sanger sequencing was done.\n\n'
    '## Results\n\n'
    '[paragraph-3] The proband carried c.1A>G.\n\n'
    '[table-0] Table 1. Variants\n\n'
    '| anchor | Patient | Variant |\n'
    '|---|---|---|\n'
    '| table-0-row-0 | P1 | c.1A>G |\n\n'
    '## References\n\n'
    '[paragraph-4] 1. Someone et al.\n\n'
    '## Table 2\n\n'
    '[table-1] Table 2. Phenotypes\n\n'
    '| anchor | Patient | Finding |\n'
    '|---|---|---|\n'
    '| table-1-row-0 | P1 | tooth agenesis |\n'
)

SUPPLEMENT = '[supp-paragraph-0] Supplementary text.\n'


@pytest.fixture
def paper_id(mocked_root_dir):
    path = document_anchored_md_path(7)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MAIN)
    return 7


def _write_supplement(paper_id: int) -> None:
    path = document_anchored_md_path(paper_id, supplement=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SUPPLEMENT)


def test_fulltext_is_the_anchored_main_text_alone_without_a_supplement(paper_id):
    assert fulltext_md(paper_id) == MAIN
    assert SUPPLEMENTARY_MATERIAL_HEADER not in fulltext_md(paper_id)


def test_fulltext_appends_the_supplement_under_the_heading_agents_are_told_about(
    paper_id,
):
    _write_supplement(paper_id)

    text = fulltext_md(paper_id, FileFormat.XLSX)

    assert text == (
        MAIN + '\n\n---\n\n# Supplementary Material (XLSX)\n\n' + SUPPLEMENT
    )


def test_fulltext_keeps_the_figures_and_legends_printed_after_the_references(
    mocked_root_dir,
):
    """The paper-85 case: an author manuscript prints its figures after
    ## REFERENCES, and the legend names patients that appear nowhere else."""
    main = (
        '## REFERENCES\n\n'
        '[paragraph-4] 1. Someone et al.\n\n'
        '[figure-3] ![Fig. 3. MRI of case 17DG0679 (STIL).](images/3.png)\n'
    )
    path = document_anchored_md_path(9)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(main)

    assert '17DG0679' in fulltext_md(9)


def test_paper_block_texts_merges_main_and_supplement(paper_id):
    _write_supplement(paper_id)

    texts = paper_block_texts(paper_id)

    assert texts['paragraph-3'] == 'The proband carried c.1A>G.'
    assert texts['table-0-row-0'] == '| P1 | c.1A>G |'
    assert texts['supp-paragraph-0'] == 'Supplementary text.'
    assert 'paragraph-99' not in texts
