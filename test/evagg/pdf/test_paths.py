"""What the agents are handed to read: the anchored documents, filtered and headed."""

import pytest

from lib.misc.pdf.anchors import paper_block_texts
from lib.misc.pdf.paths import (
    SUPPLEMENTARY_MATERIAL_HEADER,
    document_anchored_md_path,
    fulltext_md,
    relevant_sections_md,
    skip_irrelevant_sections,
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


def _classified(**relevance: bool) -> dict:
    return {
        'sections': [
            {'header': header, 'relevant': relevant}
            for header, relevant in relevance.items()
        ]
    }


def test_irrelevant_section_is_dropped_up_to_the_next_heading():
    out = skip_irrelevant_sections(MAIN, _classified(Methods=False))

    assert 'Sanger sequencing' not in out
    assert '## Methods' not in out
    assert '[paragraph-1] We report a family.' in out
    assert '[paragraph-3] The proband carried c.1A>G.' in out


def test_unmatched_heading_ends_the_skip():
    """The paper-97 case: the classifier names References but writes the table
    heading in its own words, so the table after References must survive."""
    out = skip_irrelevant_sections(MAIN, _classified(References=False))

    assert 'Someone et al.' not in out
    assert '[table-1] Table 2. Phenotypes' in out
    assert '| table-1-row-0 | P1 | tooth agenesis |' in out


def test_kept_sections_survive_byte_for_byte():
    out = skip_irrelevant_sections(MAIN, _classified(Abstract=True, Results=True))

    assert out == MAIN


def test_header_matching_ignores_case():
    out = skip_irrelevant_sections(MAIN, _classified(methods=False))

    assert 'Sanger sequencing' not in out


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


def test_relevant_sections_filters_main_only_and_keeps_the_supplement(paper_id):
    _write_supplement(paper_id)

    text = relevant_sections_md(paper_id, FileFormat.XLSX, _classified(Methods=False))

    assert 'Sanger sequencing' not in text
    assert text.endswith('# Supplementary Material (XLSX)\n\n' + SUPPLEMENT)


def test_relevant_sections_without_classifications_is_the_full_text(paper_id):
    assert relevant_sections_md(paper_id) == fulltext_md(paper_id)


def test_paper_block_texts_merges_main_and_supplement(paper_id):
    _write_supplement(paper_id)

    texts = paper_block_texts(paper_id)

    assert texts['paragraph-3'] == 'The proband carried c.1A>G.'
    assert texts['table-0-row-0'] == '| P1 | c.1A>G |'
    assert texts['supp-paragraph-0'] == 'Supplementary text.'
    assert 'paragraph-99' not in texts
