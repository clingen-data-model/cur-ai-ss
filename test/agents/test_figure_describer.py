"""The figure describer: classify every figure, describe the readable ones."""

import pytest

from lib.agents import figure_describer as describer
from lib.agents.figure_describer import (
    CLASSIFY_PROMPT,
    EVIDENCE_VISION_PROMPT,
    NOT_A_PEDIGREE,
    PEDIGREE_VISION_PROMPT,
    FigureRef,
    describe_figure,
    describe_figures,
    parse_kinds,
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
