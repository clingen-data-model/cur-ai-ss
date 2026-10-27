"""The figure describer: classify every figure, describe the readable ones."""

import pytest

from lib.agents import figure_describer as describer
from lib.agents.figure_describer import (
    CLASSIFY_PROMPT,
    EVIDENCE_VISION_PROMPT,
    LEGEND_PROMPT,
    NOT_A_PEDIGREE,
    PEDIGREE_VISION_PROMPT,
    FigureRef,
    describe_figure,
    describe_figures,
    find_legend,
    parse_kinds,
    parse_legend,
)
from lib.misc.pdf.paths import document_image_path
from lib.models.figure import FigureKind


@pytest.mark.parametrize(
    'answer, kinds',
    [
        ('Pedigree', [FigureKind.PEDIGREE]),
        ('Pedigree; Chromatogram', [FigureKind.PEDIGREE, FigureKind.CHROMATOGRAM]),
        # Order is the FigureKind order, whatever the model's.
        ('Gel, pedigree', [FigureKind.PEDIGREE, FigureKind.GEL]),
        (
            '- Copy-number plot\n- Karyotype or FISH',
            [FigureKind.COPY_NUMBER_PLOT, FigureKind.KARYOTYPE_OR_FISH],
        ),
        ('Read pileup.', [FigureKind.READ_PILEUP]),
        ('NONE', []),
        ('', []),
        (None, []),
        # A chatty answer costs a missed kind, never a wrong one.
        ('This looks like a clinical photograph', []),
        ('Chromatogram; something else', [FigureKind.CHROMATOGRAM]),
    ],
)
def test_parse_kinds(answer, kinds):
    assert parse_kinds(answer) == kinds


class _Vision:
    """A vision model scripted by prompt: the classification answer, then
    what it says to the pedigree prompt and to the evidence prompt. Records
    every prompt it was sent."""

    def __init__(
        self,
        classification: str | None,
        pedigree: str | None = 'II-1 affected female',
        evidence: str | None = 'II-1: heterozygous c.1A>G (double peak)',
    ) -> None:
        self.classification = classification
        self.pedigree = pedigree
        self.evidence = evidence
        self.prompts: list[str] = []

    def __call__(self, image_url: str, prompt: str) -> str | None:
        self.prompts.append(prompt)
        if prompt.startswith(CLASSIFY_PROMPT):
            return self.classification
        if prompt.startswith(PEDIGREE_VISION_PROMPT):
            return self.pedigree
        if prompt.startswith(EVIDENCE_VISION_PROMPT[:40]):
            return self.evidence
        raise AssertionError(f'unexpected prompt: {prompt[:60]}')


def test_a_pedigree_gets_the_pedigree_prompt_alone(monkeypatch):
    """The pedigree prompt is what it was when the pedigree was the only
    kind described: no caption, nothing appended."""
    vision = _Vision('Pedigree')
    monkeypatch.setattr(describer, 'vlm_describe', vision)

    description = describe_figure('data:', [FigureKind.PEDIGREE], 'Fig 2', None)

    assert description == 'II-1 affected female'
    assert vision.prompts == [PEDIGREE_VISION_PROMPT]


def test_evidence_kinds_get_the_evidence_prompt_with_the_caption(monkeypatch):
    vision = _Vision('Chromatogram; Gel')
    monkeypatch.setattr(describer, 'vlm_describe', vision)

    description = describe_figure(
        'data:', [FigureKind.CHROMATOGRAM, FigureKind.GEL], '(A) II-1 (B) II-2', None
    )

    assert description == 'II-1: heterozygous c.1A>G (double peak)'
    (prompt,) = vision.prompts
    assert prompt.startswith(
        'This figure shows genotyping or cytogenetic evidence (Chromatogram, Gel).'
    )
    assert 'Caption as printed in the paper:\n(A) II-1 (B) II-2' in prompt


def test_a_figure_of_both_sorts_gets_both_texts_pedigree_first(monkeypatch):
    vision = _Vision('Pedigree; Chromatogram')
    monkeypatch.setattr(describer, 'vlm_describe', vision)

    description = describe_figure(
        'data:', [FigureKind.PEDIGREE, FigureKind.CHROMATOGRAM], None, None
    )

    assert description == (
        'II-1 affected female\n\n## Genotyping evidence\n\n'
        'II-1: heterozygous c.1A>G (double peak)'
    )
    assert [p.split('\n', 1)[0][:20] for p in vision.prompts] == [
        PEDIGREE_VISION_PROMPT[:20],
        EVIDENCE_VISION_PROMPT[:20],
    ]


def test_curator_notes_reach_every_prompt(monkeypatch):
    vision = _Vision('Pedigree; Gel')
    monkeypatch.setattr(describer, 'vlm_describe', vision)
    monkeypatch.setattr(describer, 'image_to_data_url', lambda *_: 'data:')

    describe_figures(1, [FigureRef(0, False, 'cap')], notes='III-3 is the proband')

    assert len(vision.prompts) == 3
    assert all(
        'A human curator has given instructions for this run' in p
        and p.endswith('III-3 is the proband')
        for p in vision.prompts
    )


def test_no_usable_answer_drops_that_part_not_the_figure(monkeypatch):
    """A declined or truncated pedigree answer stays out (half a pedigree
    stored as authoritative is worse than none), and so does the model
    changing its mind with NOT_A_PEDIGREE; the evidence text still stands."""
    monkeypatch.setattr(describer, 'vlm_describe', _Vision('', pedigree=None))
    assert (
        describe_figure('data:', [FigureKind.PEDIGREE, FigureKind.GEL], None, None)
        == 'II-1: heterozygous c.1A>G (double peak)'
    )

    monkeypatch.setattr(
        describer, 'vlm_describe', _Vision('', pedigree=NOT_A_PEDIGREE, evidence=None)
    )
    assert (
        describe_figure('data:', [FigureKind.PEDIGREE, FigureKind.GEL], None, None)
        is None
    )


def test_describe_figures_visits_every_figure_and_keeps_the_readable_ones(monkeypatch):
    answers = iter(['NONE', 'Pedigree', 'Chromatogram', None])
    vision = _Vision('')
    vision.classification = None  # replaced per call below
    calls: list[str] = []

    def scripted(image_url: str, prompt: str) -> str | None:
        if prompt.startswith(CLASSIFY_PROMPT):
            return next(answers)
        return vision(image_url, prompt)

    monkeypatch.setattr(describer, 'vlm_describe', scripted)
    monkeypatch.setattr(
        describer, 'image_to_data_url', lambda path: calls.append(str(path)) or 'data:'
    )
    figures = [
        FigureRef(0, False, 'photo'),
        FigureRef(1, False, None),
        FigureRef(2, False, 'traces'),
        FigureRef(0, True, 'supp'),
    ]

    described = describe_figures(7, figures)

    assert [(d.image_id, d.is_supplement, d.kinds) for d in described] == [
        (1, False, [FigureKind.PEDIGREE]),
        (2, False, [FigureKind.CHROMATOGRAM]),
    ]
    assert described[0].description == 'II-1 affected female'
    # Every figure's file was loaded, from the anchored document's images/N.png.
    assert calls == [
        str(document_image_path(7, 0)),
        str(document_image_path(7, 1)),
        str(document_image_path(7, 2)),
        str(document_image_path(7, 0, supplement=True)),
    ]


def test_provider_failure_fails_the_task_instead_of_answering(monkeypatch):
    """A call that never reached the model is a task failure, not a finding."""

    def _raise(*_):
        raise RuntimeError('connection reset')

    monkeypatch.setattr(describer, 'vlm_describe', _raise)
    monkeypatch.setattr(describer, 'image_to_data_url', lambda *_: 'data:')

    with pytest.raises(RuntimeError, match='connection reset'):
        describe_figures(1, [FigureRef(0, False)])


# --- the legend question ------------------------------------------------------

_NEARBY = (
    (
        'paragraph-81',
        'We used dense surface modeling to analyze the facial morphology.',
    ),
    ('paragraph-207', 'Splicing'),
    ('paragraph-208', 'Figure 3. Mutations Identified in the ALX3 Gene'),
    ('heading', 'Figure 2. Pedigrees and Disease Localization'),
)


@pytest.mark.parametrize(
    'answer, legend',
    [
        pytest.param(
            'paragraph-208', 'Figure 3. Mutations Identified in the ALX3 Gene', id='id'
        ),
        pytest.param(
            '[paragraph-208]',
            'Figure 3. Mutations Identified in the ALX3 Gene',
            id='bracketed-id',
        ),
        pytest.param(
            'heading', 'Figure 2. Pedigrees and Disease Localization', id='heading'
        ),
        pytest.param(
            'TEXT: Figure 2. RB1 variants in tumour samples.',
            'Figure 2. RB1 variants in tumour samples.',
            id='transcribed-from-image',
        ),
        pytest.param('NONE', None, id='none'),
        pytest.param('none.', None, id='none-chatty'),
        pytest.param(None, None, id='no-answer'),
        pytest.param('TEXT:', None, id='empty-transcription'),
        # An answer in none of the three forms is a missing caption, never a
        # wrong one: a made-up id, or a block's text instead of its id.
        pytest.param('paragraph-999', None, id='unknown-id'),
        pytest.param('Figure 3. Mutations Identified', None, id='text-not-id'),
        # Only the first line counts: a justification after it is ignored.
        pytest.param(
            'paragraph-208\nIt names the ALX3 mutations shown.',
            'Figure 3. Mutations Identified in the ALX3 Gene',
            id='first-line',
        ),
    ],
)
def test_parse_legend(answer, legend):
    assert parse_legend(answer, _NEARBY) == legend


def test_find_legend_shows_the_prose_around_the_figure(monkeypatch):
    """The prompt lists every nearby block with its id, so the model can
    answer with one; the curator's notes follow as in every other prompt."""
    seen: dict = {}

    def vision(image_url, prompt):
        seen.update(image_url=image_url, prompt=prompt)
        return 'paragraph-208'

    monkeypatch.setattr(describer, 'vlm_describe', vision)

    legend = find_legend('data:img', _NEARBY, 'the proband is III-3')

    assert legend == 'Figure 3. Mutations Identified in the ALX3 Gene'
    assert seen['image_url'] == 'data:img'
    assert seen['prompt'].startswith(LEGEND_PROMPT)
    assert '[paragraph-207] Splicing' in seen['prompt']
    assert '[heading] Figure 2. Pedigrees and Disease Localization' in seen['prompt']
    assert seen['prompt'].endswith('the proband is III-3')


def test_find_legend_asks_nothing_with_nothing_to_choose_from(monkeypatch):
    monkeypatch.setattr(describer, 'vlm_describe', lambda *_: pytest.fail('asked'))

    assert find_legend('data:img', (), None) is None


def test_describe_figures_asks_the_legend_only_of_a_readable_figure_without_one(
    monkeypatch,
):
    """Three figures: one captioned (not asked), one uncaptioned and
    unreadable (not asked: it gets no row), one uncaptioned and readable
    (asked; the answer is its caption, shown to the describing prompt and
    stored on the figure)."""
    prompts: list[str] = []

    def scripted(image_url: str, prompt: str) -> str | None:
        prompts.append(prompt)
        if prompt.startswith(CLASSIFY_PROMPT):
            return 'NONE' if '[figure-1]' in image_url else 'Chromatogram'
        if prompt.startswith(LEGEND_PROMPT):
            return 'paragraph-208'
        return 'II-1 heterozygous'

    monkeypatch.setattr(describer, 'vlm_describe', scripted)
    monkeypatch.setattr(
        describer, 'image_to_data_url', lambda path: f'data:[figure-{path.stem}]'
    )
    figures = [
        FigureRef(0, False, 'Figure 1. Traces', nearby=_NEARBY),
        FigureRef(1, False, None, nearby=_NEARBY),
        FigureRef(2, False, None, nearby=_NEARBY),
    ]

    described = describe_figures(7, figures)

    assert [(d.image_id, d.caption) for d in described] == [
        (0, 'Figure 1. Traces'),
        (2, 'Figure 3. Mutations Identified in the ALX3 Gene'),
    ]
    legend_prompts = [p for p in prompts if p.startswith(LEGEND_PROMPT)]
    assert len(legend_prompts) == 1
    # The describing prompt for figure-2 was written with the found legend.
    evidence = [p for p in prompts if p.startswith(EVIDENCE_VISION_PROMPT[:40])]
    assert 'Figure 3. Mutations Identified in the ALX3 Gene' in evidence[-1]
    assert 'Figure 1. Traces' in evidence[0]
