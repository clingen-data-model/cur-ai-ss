"""The messages handlers build for their agents."""

import pytest

from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
from lib.misc.pdf.paths import document_anchored_md_path
from lib.models import GeneDB, PaperDB
from lib.models.paper import PedigreeDB
from lib.tasks.handlers import patient_extraction_message, pedigree_input


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


def test_message_carries_anchored_paper_pedigree_and_instructions(db_session, paper):
    db_session.add(
        PedigreeDB(paper_id=paper.id, image_id=3, description='II-1 affected female')
    )
    db_session.flush()

    message = patient_extraction_message(db_session, paper.id)

    assert '[paragraph-13] Eleven additional family members were affected.' in message
    assert (
        "Pedigree Description:\n{'anchor': 'figure-3', 'description': 'II-1 affected female'}"
        in message
    )
    assert message.endswith(PATIENT_EXTRACTION_AGENT_INSTRUCTIONS)
    assert message.index('Eleven') < message.index('Pedigree Description')


def test_message_without_a_pedigree_says_none(db_session, paper):
    message = patient_extraction_message(db_session, paper.id)

    assert 'Pedigree Description:\nNone\n\n' in message


def test_pedigree_input_names_the_figure_anchor():
    main = PedigreeDB(paper_id=1, image_id=2, description='d')
    supplement = PedigreeDB(paper_id=1, image_id=0, description='d', is_supplement=True)

    assert pedigree_input(main) == {'anchor': 'figure-2', 'description': 'd'}
    assert pedigree_input(supplement) == {'anchor': 'supp-figure-0', 'description': 'd'}
    assert pedigree_input(None) is None
