"""The messages handlers build for their agents."""

import pytest

from lib.agents.figure_describer import FigureRef
from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
from lib.misc.pdf.figure_text import figure_description_block
from lib.misc.pdf.paths import document_anchored_md_path
from lib.models import GeneDB, PaperDB
from lib.models.figure import FigureDescriptionDB, FigureKind
from lib.tasks.handlers import (
    cited_text,
    format_paper_context,
    paper_input,
    patient_extraction_message,
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


def test_message_is_paper_with_figures_then_instructions(db_session, paper):
    """Two user items, each ending at a prompt-cache breakpoint: the paper
    (with its gene) is the same bytes every agent sends, and every described
    figure's description is spliced into it under the figure's id; the
    instructions are the same bytes every run of this agent sends."""
    db_session.add(
        FigureDescriptionDB(
            paper_id=paper.id,
            image_id=3,
            kinds=['Pedigree'],
            description='II-1 affected female',
        )
    )
    db_session.commit()  # paper_text reads the figures in a session of its own
    path = document_anchored_md_path(paper.id)
    path.write_text(path.read_text() + '\n[figure-3] ![](x/3.png)\n')

    paper_item, instructions_item = patient_extraction_message(db_session, paper.id)

    assert {i['role'] for i in (paper_item, instructions_item)} == {'user'}
    assert paper_item['content'] == format_paper_context(
        '## Results\n\n[paragraph-13] Eleven additional family members were affected.\n'
        '\n[figure-3] ![](x/3.png)\n'
        + figure_description_block(
            FigureDescriptionDB(
                image_id=3, kinds=['Pedigree'], description='II-1 affected female'
            )
        )
        + '\n',
        'MSX1',
    )
    assert paper_item['content'].endswith('Gene: MSX1')
    assert instructions_item['content'] == PATIENT_EXTRACTION_AGENT_INSTRUCTIONS


def test_message_without_described_figures_is_the_plain_paper(db_session, paper):
    paper_item, _ = patient_extraction_message(db_session, paper.id)

    assert paper_item['content'] == format_paper_context(
        '## Results\n\n[paragraph-13] Eleven additional family members were affected.\n',
        'MSX1',
    )


def test_citation_check_accepts_a_quote_from_a_figure_description(db_session, paper):
    """A quote copied from a description checks out against its figure, and
    a quote from nowhere still does not."""
    from lib.models.evidence_block import CitationError, EvidenceBlock
    from lib.tasks.handlers import citation_check

    path = document_anchored_md_path(paper.id)
    path.write_text(path.read_text() + '\n[figure-3] ![Fig 2. The family](x/3.png)\n')
    db_session.add(
        FigureDescriptionDB(
            paper_id=paper.id,
            image_id=3,
            kinds=['Pedigree'],
            description='II-1 affected female\n\nII-2 unaffected male',
        )
    )
    db_session.commit()
    check = citation_check(paper.id)

    def block(quote: str) -> EvidenceBlock:
        return EvidenceBlock(
            value='x', reasoning='r', citations=[{'anchor': 'figure-3', 'quote': quote}]
        )

    check(block(''))
    check(block('The family'))
    check(block('II-2 unaffected male'))
    with pytest.raises(CitationError):
        check(block('III-9 affected'))


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


def test_paper_figures_lists_every_figure_with_an_image_main_first(paper):
    """The figures the describer visits: each figure-N anchor whose
    images/N.png exists, main text before supplement, with the alt text the
    anchored document carries as its caption (None when it has none)."""
    from lib.misc.pdf.anchors import Anchor, write_anchored
    from lib.misc.pdf.paths import document_image_path
    from lib.tasks.handlers import paper_figures

    write_anchored(
        paper.id,
        '[figure-0] ![Figure 1. Photographs](x/0.png)\n\n'
        '[paragraph-1] text\n\n'
        '[figure-2] ![](x/2.png)\n\n'
        '[figure-3] ![no file](x/3.png)\n',
        [
            Anchor(id='figure-0'),
            Anchor(id='paragraph-1'),
            Anchor(id='figure-2'),
            Anchor(id='figure-3'),
        ],
    )
    write_anchored(
        paper.id,
        '[supp-figure-0] ![Figure S1](x/0.png)\n',
        [Anchor(id='supp-figure-0')],
        supplement=True,
    )
    for image_id, supplement in ((0, False), (2, False), (0, True)):
        path = document_image_path(paper.id, image_id, supplement=supplement)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'png')

    assert paper_figures(paper.id) == [
        FigureRef(0, False, 'Figure 1. Photographs'),
        FigureRef(2, False, None),
        FigureRef(0, True, 'Figure S1'),
    ]


async def test_figure_description_stores_one_row_per_described_figure(
    monkeypatch, db_session, paper
):
    """The handler hands every figure and the curator's notes to the describer
    and replaces the paper's rows with what came back, kinds and the caption
    the model was shown included."""
    from lib.agents.figure_describer import DescribedFigure
    from lib.tasks import handlers
    from lib.tasks.models import TaskDB, TaskStatus, TaskType

    db_session.add(
        FigureDescriptionDB(
            paper_id=paper.id, image_id=9, kinds=['Pedigree'], description='stale'
        )
    )
    task = TaskDB(
        paper_id=paper.id,
        type=TaskType.FIGURE_DESCRIPTION,
        status=TaskStatus.RUNNING,
        additional_context='III-3 is the proband',
    )
    db_session.add(task)
    db_session.commit()
    figures = [FigureRef(1, False, None), FigureRef(2, False, 'traces')]
    seen: dict = {}

    def fake_describe(paper_id, figs, notes):
        seen.update(paper_id=paper_id, figures=figs, notes=notes)
        return [
            DescribedFigure(
                image_id=2,
                is_supplement=False,
                kinds=[FigureKind.PEDIGREE, FigureKind.GEL],
                caption='traces',
                description='pedigree and digest',
            )
        ]

    monkeypatch.setattr(handlers, 'paper_figures', lambda paper_id: figures)
    monkeypatch.setattr(handlers, 'describe_figures', fake_describe)

    await handlers.handle_figure_description(task.id)
    db_session.expire_all()

    assert seen == {
        'paper_id': paper.id,
        'figures': figures,
        'notes': 'III-3 is the proband',
    }
    rows = db_session.query(FigureDescriptionDB).filter_by(paper_id=paper.id).all()
    assert [(r.image_id, r.kinds, r.caption, r.description) for r in rows] == [
        (2, ['Pedigree', 'Gel'], 'traces', 'pedigree and digest')
    ]


# --- A curator's note on a fresh run (inherited, or own with no conversation)


class _ItemsSession:
    def __init__(self, items):
        self.items = items
        self.cleared = False

    async def get_items(self, limit=None):
        return self.items[:limit] if limit else self.items

    async def clear_session(self) -> None:
        self.cleared = True


async def test_a_note_is_a_follow_up_only_for_its_own_task_with_a_conversation():
    from lib.tasks.handlers import continues_conversation
    from lib.tasks.models import TaskType

    note = 'III-3 is the proband'
    assert await continues_conversation(_ItemsSession([{'role': 'user'}]), note, None)
    # Inherited from a predecessor: the inputs just changed, so never a follow-up.
    assert not await continues_conversation(
        _ItemsSession([{'role': 'user'}]), note, TaskType.PATIENT_EXTRACTION
    )
    # Own note but nothing to follow up on (a retry cleared the session).
    assert not await continues_conversation(_ItemsSession([]), note, None)


def test_curator_note_section_names_the_step_an_inherited_note_was_given_to():
    from lib.tasks.handlers import curator_note_section
    from lib.tasks.models import TaskType

    inherited = curator_note_section('Use Brazil.', TaskType.PATIENT_DEMOGRAPHICS)
    assert inherited.startswith(
        'This user-provided context was supplied to Patient Demographics, '
    )
    assert 'might also be relevant here' in inherited
    assert inherited.endswith('\nUse Brazil.')
    own = curator_note_section('Use Brazil.', None)
    assert own.startswith('A human curator re-ran this step')
    assert own.endswith('\nUse Brazil.')
    for root in (TaskType.PDF_PARSING, TaskType.PAPER_CLASSIFIER):
        whole = curator_note_section('Use Brazil.', root)
        assert whole.startswith(
            'This user-provided context was given for this re-run of the whole paper'
        )
        assert whole.endswith('\nUse Brazil.')


def test_with_curator_note_appends_an_item_or_a_section_and_leaves_none_alone():
    from lib.tasks.handlers import paper_input, with_curator_note
    from lib.tasks.models import TaskType

    items = paper_input('PAPER', 'INSTRUCTIONS', 'DATA')
    assert with_curator_note(items, None, None) is items
    with_note = with_curator_note(items, 'Use Brazil.', TaskType.PATIENT_EXTRACTION)
    assert isinstance(with_note, list)
    assert [i['content'] for i in with_note[:3]] == ['PAPER', 'INSTRUCTIONS', 'DATA']
    assert str(with_note[3]['content']).endswith('\nUse Brazil.')
    assert 'supplied to Patient Extraction' in str(with_note[3]['content'])

    text = with_curator_note('Variant JSON: {}', 'Use GRCh37.', None)
    assert isinstance(text, str)
    assert text.startswith('Variant JSON: {}\n\nA human curator re-ran this step')


async def test_patient_extraction_runs_fresh_with_an_inherited_note_last(
    monkeypatch, db_session, paper
):
    """A note that came down from Figure Description starts a fresh run whose
    first message ends with the note, labelled as supplied to that step."""
    from types import SimpleNamespace

    from lib.tasks import handlers
    from lib.tasks.models import TaskDB, TaskStatus, TaskType

    session = _ItemsSession([{'role': 'user', 'content': 'an old conversation'}])
    seen: dict = {}

    async def fake_run(agent, message, check, session):
        seen['message'] = message
        return SimpleNamespace(
            final_output=_flag_output(['Patient 1'], []), raw_responses=[]
        )

    monkeypatch.setattr(handlers, 'run_with_checked_output', fake_run)
    monkeypatch.setattr(handlers, 'agent_session', lambda task_id: session)
    monkeypatch.setattr(handlers, 'citation_check', lambda paper_id: None)
    monkeypatch.setattr(handlers, 'log_run_metrics', lambda *a, **k: None)
    task = TaskDB(
        paper_id=paper.id,
        type=TaskType.PATIENT_EXTRACTION,
        status=TaskStatus.RUNNING,
        additional_context='Read every figure for family members.',
        context_origin=TaskType.FIGURE_DESCRIPTION,
    )
    db_session.add(task)
    db_session.commit()

    await handlers.handle_patient_extraction(task.id)

    assert session.cleared
    message = seen['message']
    assert isinstance(message, list)
    assert message[0]['content'].startswith('PAPER AND GENE CONTEXT')
    last = str(message[-1]['content'])
    assert last.startswith(
        'This user-provided context was supplied to Figure Description'
    )
    assert last.endswith('\nRead every figure for family members.')
    assert 'review your previous analysis' not in last


async def test_figure_description_labels_an_inherited_note(
    monkeypatch, db_session, paper
):
    """The describer has no conversation, so an inherited note joins its
    vision prompts with the same label the agents get."""
    from lib.tasks import handlers
    from lib.tasks.models import TaskDB, TaskStatus, TaskType

    task = TaskDB(
        paper_id=paper.id,
        type=TaskType.FIGURE_DESCRIPTION,
        status=TaskStatus.RUNNING,
        additional_context='Six pedigrees over three figures.',
        context_origin=TaskType.PDF_PARSING,
    )
    db_session.add(task)
    db_session.commit()
    seen: dict = {}

    def fake_describe(paper_id, figs, notes):
        seen['notes'] = notes
        return []

    monkeypatch.setattr(handlers, 'paper_figures', lambda paper_id: [])
    monkeypatch.setattr(handlers, 'describe_figures', fake_describe)

    await handlers.handle_figure_description(task.id)

    # Its only ancestors are the two root tasks, so an inherited note is by
    # construction one for the whole re-run.
    assert seen['notes'].startswith(
        'This user-provided context was given for this re-run of the whole paper'
    )
    assert seen['notes'].endswith('\nSix pedigrees over three figures.')
