"""The messages handlers build for their agents."""

import pytest

from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
from lib.misc.pdf.paths import document_anchored_md_path
from lib.models import GeneDB, PaperDB
from lib.models.paper import PedigreeDB
from lib.tasks.handlers import (
    format_paper_context,
    paper_input,
    patient_extraction_message,
    pedigree_input,
)


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='MSX1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(content_hash='abc123', gene_id=gene.id, filename='msx1.pdf')
    db_session.add(paper)
    db_session.flush()
    path = document_anchored_md_path(paper.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '## Results\n\n[paragraph-13] Eleven additional family members were affected.\n'
    )
    return paper


def test_message_is_paper_then_instructions_then_pedigree(db_session, paper):
    """Three user items, each ending at a prompt-cache breakpoint: the paper
    (with its gene) is the same bytes every agent sends; the instructions are
    the same bytes every run of this agent sends; the pedigree is this run's
    data and comes last, which is also where the instructions say it is
    ("provided below")."""
    db_session.add(
        PedigreeDB(paper_id=paper.id, image_id=3, description='II-1 affected female')
    )
    db_session.flush()

    paper_item, instructions_item, data_item = patient_extraction_message(
        db_session, paper.id
    )

    assert {i['role'] for i in (paper_item, instructions_item, data_item)} == {'user'}
    assert paper_item['content'] == format_paper_context(
        '## Results\n\n[paragraph-13] Eleven additional family members were affected.\n',
        'MSX1',
    )
    assert paper_item['content'].endswith('Gene: MSX1')
    assert instructions_item['content'] == PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert data_item['content'] == (
        "Pedigree Description:\n{'anchor': 'figure-3', 'description': 'II-1 affected female'}"
    )


def test_message_without_a_pedigree_says_none(db_session, paper):
    *_, data_item = patient_extraction_message(db_session, paper.id)

    assert data_item['content'] == 'Pedigree Description:\nNone'


def test_paper_input_with_and_without_data():
    paper = 'PAPER AND GENE CONTEXT\n\nPaper (fulltext md):\nx\n\nGene: G'

    assert paper_input(paper, 'rules', 'Patient JSON:\n{}') == [
        {'role': 'user', 'content': paper},
        {'role': 'user', 'content': 'rules'},
        {'role': 'user', 'content': 'Patient JSON:\n{}'},
    ]
    assert paper_input(paper, 'rules') == [
        {'role': 'user', 'content': paper},
        {'role': 'user', 'content': 'rules'},
    ]


def test_pedigree_input_names_the_figure_anchor():
    main = PedigreeDB(paper_id=1, image_id=2, description='d')
    supplement = PedigreeDB(paper_id=1, image_id=0, description='d', is_supplement=True)

    assert pedigree_input(main) == {'anchor': 'figure-2', 'description': 'd'}
    assert pedigree_input(supplement) == {'anchor': 'supp-figure-0', 'description': 'd'}
    assert pedigree_input(None) is None


def test_citation_check_reads_the_paper_once_and_rejects_bad_citations(paper):
    from lib.models.evidence_block import Citation, CitationError, EvidenceBlock
    from lib.tasks.handlers import citation_check

    check = citation_check(paper.id)
    good = EvidenceBlock[str](
        value='x',
        reasoning='r',
        citations=[Citation(anchor='paragraph-13', quote='Eleven additional')],
    )
    bad = EvidenceBlock[str](
        value='x', reasoning='r', citations=[Citation(anchor='paragraph-14')]
    )

    check(good)
    with pytest.raises(CitationError, match="anchor 'paragraph-14' does not exist"):
        check([good, bad])
