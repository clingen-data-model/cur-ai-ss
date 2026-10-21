"""The messages handlers build for their agents."""

import pytest

from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
from lib.misc.pdf.paths import document_anchored_md_path
from lib.models import GeneDB, PaperDB
from lib.models.paper import PedigreeDB
from lib.tasks.handlers import (
    cited_text,
    format_paper_context,
    paper_global_context,
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


def test_cited_text_renders_each_citation_as_quote_then_anchor():
    """A stored block's citations, as the later agents are shown them: the
    quote with its anchor in parentheses, or the bare anchor when there is no
    quote (a figure), joined with '; '."""
    block = {
        'value': 'P1',
        'reasoning': 'r',
        'citations': [
            {'anchor': 'paragraph-13', 'quote': 'Eleven additional'},
            {'anchor': 'figure-2', 'quote': ''},
            {'anchor': 'table-1-row-2'},
        ],
    }

    assert (
        cited_text(block) == 'Eleven additional (paragraph-13); figure-2; table-1-row-2'
    )


def test_cited_text_is_empty_without_citations():
    assert cited_text({'value': 'P1', 'reasoning': 'r', 'citations': []}) == ''
    # A row written before citations existed carries only the retired keys.
    assert cited_text({'value': 'P1', 'reasoning': 'r', 'quote': 'old'}) == ''


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


def _flag_output(patients: list[str], flags: list[dict]):
    from lib.models.patient import (
        FamilyEntry,
        PatientExtractionOutput,
        PatientIdentity,
        ProbandStatus,
    )

    def block(value: object) -> dict:
        return {
            'value': value,
            'reasoning': 'test',
            'citations': [{'anchor': 'paragraph-13', 'quote': 'Eleven'}],
        }

    return PatientExtractionOutput(
        patients=[
            PatientIdentity(
                identifier=block(p),
                family_identifier=block('Family 1'),
                proband_status=block(
                    ProbandStatus.Proband if i == 0 else ProbandStatus.Non_proband
                ),
            )
            for i, p in enumerate(patients)
        ],
        families=[
            FamilyEntry(
                family={'identifier': block('Family 1'), 'consanguinity': block(False)},
                patient_identifiers=[block(p) for p in patients],
            )
        ],
        flags=flags,
    )


@pytest.fixture
def run_patient_extraction(monkeypatch, db_session, paper):
    """Drive handle_patient_extraction with a canned agent output: the agent
    call, its session and the citation check are stubbed, the DB is real."""
    from types import SimpleNamespace

    from lib.tasks import handlers
    from lib.tasks.models import TaskDB, TaskStatus, TaskType

    class _Session:
        async def clear_session(self) -> None:
            pass

    async def run(output):
        async def fake_run(agent, message, check, session):
            return SimpleNamespace(final_output=output, raw_responses=[])

        monkeypatch.setattr(handlers, 'run_with_checked_output', fake_run)
        monkeypatch.setattr(handlers, 'agent_session', lambda task_id: _Session())
        monkeypatch.setattr(handlers, 'citation_check', lambda paper_id: None)
        monkeypatch.setattr(handlers, 'log_run_metrics', lambda *a, **k: None)
        task = TaskDB(
            paper_id=paper.id,
            type=TaskType.PATIENT_EXTRACTION,
            status=TaskStatus.RUNNING,
        )
        db_session.add(task)
        db_session.commit()
        await handlers.handle_patient_extraction(task.id)
        db_session.expire_all()

    return run


async def test_patient_extraction_persists_flags_and_links_them_to_patients(
    db_session, paper, run_patient_extraction
):
    from lib.models import FamilyDB, FlagDB, PatientDB

    await run_patient_extraction(
        _flag_output(
            ['Patient 1', 'Patient 2'],
            [
                {
                    'kind': 'excluded',
                    'about': 'Patient 2',
                    'flag': {
                        'value': 'status implied',
                        'reasoning': 'affected only by pedigree shading',
                        'citations': [{'anchor': 'figure-1', 'quote': ''}],
                    },
                },
                {
                    'kind': 'excluded',
                    'about': None,
                    'flag': {
                        'value': 'untested sister',
                        'reasoning': 'mentioned once, nothing stated',
                        'citations': [{'anchor': 'paragraph-13', 'quote': 'Eleven'}],
                    },
                },
                {
                    'kind': 'excluded',
                    'about': 'family 1',
                    'flag': {
                        'value': 'no proband marked',
                        'reasoning': 'chose the first described',
                        'citations': [{'anchor': 'paragraph-13', 'quote': 'Eleven'}],
                    },
                },
            ],
        )
    )

    p2 = db_session.query(PatientDB).filter_by(identifier='Patient 2').one()
    family = db_session.query(FamilyDB).filter_by(paper_id=paper.id).one()
    rows = db_session.query(FlagDB).filter_by(paper_id=paper.id).order_by(FlagDB.id)
    assert [(r.subject, r.patient_id, r.family_id, r.source) for r in rows] == [
        ('status implied', p2.id, None, 'PATIENT_EXTRACTION'),
        ('untested sister', None, None, 'PATIENT_EXTRACTION'),
        ('no proband marked', None, family.id, 'PATIENT_EXTRACTION'),
    ]


async def test_rerunning_patient_extraction_replaces_only_its_own_flags(
    db_session, paper, run_patient_extraction
):
    from lib.models import FlagDB

    other_agent = FlagDB(
        paper_id=paper.id,
        source='VARIANT_EXTRACTION',
        kind='excluded',
        subject='kept',
        evidence={'value': 'kept', 'reasoning': 'x', 'citations': []},
    )
    db_session.add(other_agent)
    db_session.commit()

    sister = {
        'kind': 'excluded',
        'about': None,
        'flag': {
            'value': 'untested sister',
            'reasoning': 'mentioned once',
            'citations': [{'anchor': 'paragraph-13', 'quote': 'Eleven'}],
        },
    }
    await run_patient_extraction(_flag_output(['Patient 1'], [sister]))
    await run_patient_extraction(_flag_output(['Patient 1'], []))

    rows = db_session.query(FlagDB).filter_by(paper_id=paper.id).all()
    assert [r.subject for r in rows] == ['kept']


def test_paper_context_carries_curator_notes_after_the_gene():
    """The notes ride in the paper block, so every agent on the paper sends the
    same bytes and the shared prompt-cache prefix still holds."""
    plain = format_paper_context('text', 'MSX1')
    noted = format_paper_context('text', 'MSX1', 'Ignore the supplement cohort.')

    assert noted.startswith(plain)
    assert noted.endswith(
        'A human curator is re-running the extraction of this paper and has '
        'given additional instructions for the whole run. Follow them where '
        'they bear on your task:\nIgnore the supplement cohort.'
    )
    assert format_paper_context('text', 'MSX1', None) == plain
    assert format_paper_context('text', 'MSX1', '') == plain


def test_paper_global_context_reads_the_paper_row(db_session, paper):
    assert paper_global_context(paper.id) is None
    assert paper_global_context(paper.id + 1000) is None

    paper.paper_global_additional_context = 'Patients are numbered per family.'
    db_session.commit()

    assert paper_global_context(paper.id) == 'Patients are numbered per family.'
