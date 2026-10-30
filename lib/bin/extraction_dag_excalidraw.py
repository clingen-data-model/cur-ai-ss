"""Draw the extraction pipeline as an Excalidraw file for curators.

    uv run python -m lib.bin.extraction_dag_excalidraw > docs/extraction-dag.excalidraw

The nodes and edges come from ``TaskType`` and ``TASK_SUCCESSORS`` in
lib.tasks.models, so the drawing cannot drift from the graph the worker runs:
``test/bin/test_extraction_dag_excalidraw.py`` fails when an edge gains or
loses a label here, or when the committed file is stale. What each edge
carries and what each step writes are facts the code does not state in one
place, so they are spelled out in ``EDGE_LABELS`` and ``NODE_NOTES`` below;
``TaskType.description`` supplies the one-sentence purpose.

Open the output at https://excalidraw.com (menu, Open), or with the VS Code
Excalidraw extension. Deterministic: ids and seeds are derived from names, so
regenerating without a change produces an identical file.
"""

from __future__ import annotations

import json
import sys
import textwrap
import zlib
from typing import Any

from lib.tasks.models import TASK_SUCCESSORS, TaskType

T = TaskType

# What the completed step hands the next one. Keyed by (predecessor, successor);
# every TASK_SUCCESSORS edge must have an entry (the test checks).
EDGE_LABELS: dict[tuple[TaskType, TaskType], str] = {
    (T.PDF_PARSING, T.PAPER_CLASSIFIER): 'anchored text, tables, figure images',
    (T.PAPER_CLASSIFIER, T.PAPER_METADATA): 'relevant: paper text',
    (T.PAPER_CLASSIFIER, T.VARIANT_EXTRACTION): 'relevant: paper text + target gene',
    (T.PAPER_CLASSIFIER, T.FIGURE_DESCRIPTION): (
        'relevant: each figure image, its caption, the text around it'
    ),
    (T.FIGURE_DESCRIPTION, T.PATIENT_EXTRACTION): (
        'paper text with every figure description spliced under its [figure-N]'
    ),
    (T.PATIENT_EXTRACTION, T.PATIENT_DEMOGRAPHICS): (
        "one task per patient: Patient JSON + the family's proband identifier"
    ),
    (T.PATIENT_EXTRACTION, T.PATIENT_VARIANT_OCCURRENCES): (
        'patient ids, identifiers and their citations (no demographics)'
    ),
    (T.PAPER_METADATA, T.PAPER_MONDO_LINKING): "the paper's disease name",
    (T.VARIANT_EXTRACTION, T.VARIANT_HARMONIZATION): (
        "one task per variant: the row's plain fields (hgvs c/p/g, transcript, rsID)"
    ),
    (T.VARIANT_EXTRACTION, T.PATIENT_VARIANT_OCCURRENCES): (
        'variant ids and each variant as the paper writes it'
    ),
    (T.VARIANT_HARMONIZATION, T.VARIANT_ANNOTATION): (
        'harmonized variant: HGVS g/c/p, rsID, ClinGen allele id'
    ),
    (T.VARIANT_ANNOTATION, T.EXTRACTION_VERIFICATION): 'flags',
    (T.PATIENT_DEMOGRAPHICS, T.PHENOTYPE_EXTRACTION): (
        'one task per patient not marked Unaffected: patient identity'
    ),
    (T.PATIENT_DEMOGRAPHICS, T.SEGREGATION_EVIDENCE_EXTRACTION): (
        'affected status, sex, proband status of every family member '
        "(queued once the last patient's run is in)"
    ),
    (T.PATIENT_VARIANT_OCCURRENCES, T.SEGREGATION_EVIDENCE_EXTRACTION): (
        "the family's patient-variant links with zygosity (fan-in with demographics)"
    ),
    (T.PATIENT_VARIANT_OCCURRENCES, T.COMPOUND_HET_EVALUATION): (
        "one task per patient with two or more heterozygous links; the parents' links"
    ),
    (T.PATIENT_VARIANT_OCCURRENCES, T.PAPER_MONDO_LINKING): (
        "re-link: a case may have changed the paper's disease name"
    ),
    (T.PATIENT_VARIANT_OCCURRENCES, T.OCCURRENCE_MONDO_LINKING): (
        'one task per occurrence: its own disease name'
    ),
    (T.SEGREGATION_EVIDENCE_EXTRACTION, T.SEGREGATION_ANALYSIS_COMPUTED): (
        "extracted LOD score and segregation statements + the family's patients and links"
    ),
    (T.SEGREGATION_ANALYSIS_COMPUTED, T.EXTRACTION_VERIFICATION): 'flags',
    (T.PHENOTYPE_EXTRACTION, T.HPO_LINKING): (
        'one task per phenotype the HPO link cache has not already linked: its text'
    ),
    (T.HPO_LINKING, T.EXTRACTION_VERIFICATION): 'flags',
    (T.PAPER_MONDO_LINKING, T.EXTRACTION_VERIFICATION): 'flags',
    (T.OCCURRENCE_MONDO_LINKING, T.EXTRACTION_VERIFICATION): 'flags',
}

# Edges drawn dashed: verification is queued by the worker when every other
# task of the paper has settled, not by the edge (lib.tasks.models.TaskType).
DASHED_TARGETS = {T.EXTRACTION_VERIFICATION}

# (runs on, writes) per step. "Runs on" names the configured model setting
# (lib.core.environment) or the non-model code that does the work.
NODE_NOTES: dict[TaskType, tuple[str, str]] = {
    T.PDF_PARSING: (
        'Docling; VLM_MODEL corrects misread tables',
        'documents/<paper>/main|supplement: anchored.md, anchors.json, tables/, images/',
    ),
    T.PAPER_CLASSIFIER: (
        'EXTRACTION_MODEL',
        'papers.is_paper_relevant + its basis; a "no" ends the pipeline',
    ),
    T.PAPER_METADATA: (
        'EXTRACTION_MODEL + PubMed',
        'papers: title, authors, journal, year, PMID, disease name',
    ),
    T.VARIANT_EXTRACTION: (
        'EXTRACTION_MODEL',
        'variants rows as written: hgvs, type, functional evidence; flags',
    ),
    T.FIGURE_DESCRIPTION: (
        'VLM_MODEL',
        'figure_descriptions: kind, caption, description per readable figure',
    ),
    T.PATIENT_EXTRACTION: (
        'EXTRACTION_MODEL',
        'patients (identifier, proband status), families; flags',
    ),
    T.PATIENT_DEMOGRAPHICS: (
        'EXTRACTION_MODEL, per patient',
        'patients: sex, ages, onset, country, ancestry, race, affected status, relationship',
    ),
    T.SEGREGATION_EVIDENCE_EXTRACTION: (
        'EXTRACTION_MODEL, per family',
        'segregation_evidence: LOD score, statements, per family',
    ),
    T.SEGREGATION_ANALYSIS_COMPUTED: (
        'deterministic (no model), per family',
        'segregation_analysis_computed: counts and points per family',
    ),
    T.VARIANT_HARMONIZATION: (
        'EXTRACTION_MODEL + ClinVar, Allele Registry, VariantValidator; per variant',
        'variants: harmonized HGVS g/c/p, rsID, CAid, coordinates',
    ),
    T.VARIANT_ANNOTATION: (
        'tools (SpliceAI, gnomAD), per variant',
        'variants: annotation columns',
    ),
    T.PATIENT_VARIANT_OCCURRENCES: (
        'EXTRACTION_MODEL',
        'patient_variant_occurrences: zygosity, inheritance mechanism, variant '
        'inheritance, testing methods, disease name; flags',
    ),
    T.COMPOUND_HET_EVALUATION: (
        'EXTRACTION_MODEL, per patient',
        'occurrence pairing (paired_occurrence_id); flags',
    ),
    T.PHENOTYPE_EXTRACTION: (
        'EXTRACTION_MODEL, per patient',
        'phenotypes: concept, onset, severity, negated/uncertain, per patient',
    ),
    T.HPO_LINKING: (
        'LINKING_MODEL, per phenotype',
        'hpos: candidate HPO terms with confidence; HPO link cache',
    ),
    T.PAPER_MONDO_LINKING: ('LINKING_MODEL', 'papers: MONDO id for the disease name'),
    T.OCCURRENCE_MONDO_LINKING: (
        'LINKING_MODEL, per occurrence',
        "patient_variant_occurrences: MONDO id for the link's disease name",
    ),
    T.EXTRACTION_VERIFICATION: (
        'deterministic (no model); queued by the worker when everything else has settled',
        "flags merged; completion snapshot and the owner's email",
    ),
}

# Grid position (column, row) per step. Rows follow the longest path from PDF
# Parsing; columns are chosen by hand to keep arrows short.
GRID: dict[TaskType, tuple[int, int]] = {
    T.PDF_PARSING: (3, 0),
    T.PAPER_CLASSIFIER: (3, 1),
    T.PAPER_METADATA: (0, 2),
    T.VARIANT_EXTRACTION: (2, 2),
    T.FIGURE_DESCRIPTION: (4, 2),
    T.VARIANT_HARMONIZATION: (1, 3),
    T.PATIENT_EXTRACTION: (4, 3),
    T.VARIANT_ANNOTATION: (1, 4),
    T.PATIENT_VARIANT_OCCURRENCES: (3, 4),
    T.PATIENT_DEMOGRAPHICS: (5, 4),
    T.PAPER_MONDO_LINKING: (0, 5),
    T.OCCURRENCE_MONDO_LINKING: (2, 5),
    T.COMPOUND_HET_EVALUATION: (3, 5),
    T.SEGREGATION_EVIDENCE_EXTRACTION: (4, 5),
    T.PHENOTYPE_EXTRACTION: (6, 5),
    T.SEGREGATION_ANALYSIS_COMPUTED: (4, 6),
    T.HPO_LINKING: (6, 6),
    T.EXTRACTION_VERIFICATION: (3, 7),
}

# Fill colour by the scope the task runs over (TaskType.scope_column).
SCOPE_COLOURS: dict[str | None, tuple[str, str]] = {
    None: ('#e9ecef', 'whole paper'),
    'patient_id': ('#d0ebff', 'per patient'),
    'family_id': ('#d3f9d8', 'per family'),
    'variant_id': ('#ffe8cc', 'per variant'),
    'phenotype_id': ('#e5dbff', 'per phenotype'),
    'patient_variant_occurrence_id': ('#ffdeeb', 'per patient-variant occurrence'),
}

NODE_W = 330
COL_GAP = 60
ROW_GAP = 150
TITLE_SIZE = 20
BODY_SIZE = 13
LINE = 1.25
PAD = 12
WRAP = 46  # characters per body line at BODY_SIZE within NODE_W


def _seed(name: str) -> int:
    return zlib.crc32(name.encode()) & 0x7FFFFFFF


def _base(kind: str, ident: str, x: float, y: float, w: float, h: float) -> dict:
    return {
        'id': ident,
        'type': kind,
        'x': x,
        'y': y,
        'width': w,
        'height': h,
        'angle': 0,
        'strokeColor': '#1e1e1e',
        'backgroundColor': 'transparent',
        'fillStyle': 'solid',
        'strokeWidth': 1,
        'strokeStyle': 'solid',
        'roughness': 1,
        'opacity': 100,
        'groupIds': [],
        'frameId': None,
        'roundness': None,
        'seed': _seed(ident),
        'version': 1,
        'versionNonce': _seed(ident + '#'),
        'isDeleted': False,
        'boundElements': [],
        'updated': 1,
        'link': None,
        'locked': False,
    }


def _text(
    ident: str,
    text: str,
    x: float,
    y: float,
    size: int,
    *,
    width: float,
    family: int = 2,
    align: str = 'left',
    container: str | None = None,
) -> dict:
    lines = text.split('\n')
    el = _base('text', ident, x, y, width, len(lines) * size * LINE)
    el.update(
        {
            'text': text,
            'originalText': text,
            'fontSize': size,
            'fontFamily': family,
            'textAlign': align,
            'verticalAlign': 'middle' if container else 'top',
            'containerId': container,
            'lineHeight': LINE,
            'autoResize': True,
        }
    )
    return el


def _slug(task: TaskType) -> str:
    return task.name.lower().replace('_', '-')


def _body(task: TaskType) -> str:
    runs_on, writes = NODE_NOTES[task]
    scope_label = SCOPE_COLOURS[task.scope_column][1]
    parts = [
        textwrap.fill(task.description, WRAP),
        textwrap.fill(f'Runs on: {runs_on}', WRAP),
        textwrap.fill(f'Writes: {writes}', WRAP),
        f'Scope: {scope_label}',
    ]
    return '\n\n'.join(parts)


def build() -> dict[str, Any]:
    """The Excalidraw document as a dict."""
    bodies = {task: _body(task) for task in TaskType}
    body_lines = {task: body.count('\n') + 1 for task, body in bodies.items()}
    row_heights: dict[int, float] = {}
    for task, (_, row) in GRID.items():
        h = PAD + TITLE_SIZE * LINE + 8 + body_lines[task] * BODY_SIZE * LINE + PAD
        row_heights[row] = max(row_heights.get(row, 0), h)
    row_top: dict[int, float] = {}
    y = 0.0
    for row in sorted(row_heights):
        row_top[row] = y
        y += row_heights[row] + ROW_GAP

    elements: list[dict] = []
    rects: dict[TaskType, dict] = {}
    for task in TaskType:
        col, row = GRID[task]
        x = col * (NODE_W + COL_GAP)
        top = row_top[row]
        h = row_heights[row]
        rect = _base('rectangle', f'node-{_slug(task)}', x, top, NODE_W, h)
        rect['backgroundColor'] = SCOPE_COLOURS[task.scope_column][0]
        rect['roundness'] = {'type': 3}
        rect['groupIds'] = [f'group-{_slug(task)}']
        title = _text(
            f'title-{_slug(task)}',
            task.value,
            x + PAD,
            top + PAD,
            TITLE_SIZE,
            width=NODE_W - 2 * PAD,
            family=1,
        )
        body = _text(
            f'body-{_slug(task)}',
            bodies[task],
            x + PAD,
            top + PAD + TITLE_SIZE * LINE + 8,
            BODY_SIZE,
            width=NODE_W - 2 * PAD,
        )
        title['groupIds'] = body['groupIds'] = rect['groupIds']
        rects[task] = rect
        elements += [rect, title, body]

    for src, dsts in TASK_SUCCESSORS.items():
        for dst in dsts:
            a, b = rects[src], rects[dst]
            sx, sy = a['x'] + a['width'] / 2, a['y'] + a['height']
            ex, ey = b['x'] + b['width'] / 2, b['y']
            ident = f'edge-{_slug(src)}--{_slug(dst)}'
            arrow = _base('arrow', ident, sx, sy, ex - sx, ey - sy)
            arrow.update(
                {
                    'points': [[0, 0], [ex - sx, ey - sy]],
                    'lastCommittedPoint': None,
                    'startBinding': {'elementId': a['id'], 'focus': 0, 'gap': 4},
                    'endBinding': {'elementId': b['id'], 'focus': 0, 'gap': 4},
                    'startArrowhead': None,
                    'endArrowhead': 'arrow',
                    'elbowed': False,
                    'roundness': {'type': 2},
                    'strokeStyle': 'dashed' if dst in DASHED_TARGETS else 'solid',
                }
            )
            label_text = textwrap.fill(EDGE_LABELS[(src, dst)], 34)
            label = _text(
                f'label-{_slug(src)}--{_slug(dst)}',
                label_text,
                (sx + ex) / 2 - 110,
                (sy + ey) / 2 - 10,
                11,
                width=220,
                align='center',
                container=ident,
            )
            arrow['boundElements'] = [{'id': label['id'], 'type': 'text'}]
            a['boundElements'].append({'id': ident, 'type': 'arrow'})
            b['boundElements'].append({'id': ident, 'type': 'arrow'})
            elements += [arrow, label]

    legend_y = row_top[max(row_top)] + row_heights[max(row_top)] + ROW_GAP
    legend_lines = [
        'Each box is one pipeline step; an arrow is "when this completes, queue that",',
        'labelled with what the next step is given. Dashed arrows: Extraction Verification',
        'is queued by the worker once every other task of the paper has settled.',
        'Fill colour is the scope a step runs over: one task row per paper, patient, ...',
    ]
    legend = _text(
        'legend', '\n'.join(legend_lines), 0, legend_y, BODY_SIZE, width=NODE_W * 2
    )
    swatch_x = 2 * (NODE_W + COL_GAP) + 40
    elements.append(legend)
    for i, (colour, scope_label) in enumerate(SCOPE_COLOURS.values()):
        sw = _base('rectangle', f'swatch-{i}', swatch_x, legend_y + i * 28, 60, 20)
        sw['backgroundColor'] = colour
        lb = _text(
            f'swatch-label-{i}',
            scope_label,
            swatch_x + 72,
            legend_y + i * 28,
            BODY_SIZE,
            width=300,
        )
        elements += [sw, lb]

    return {
        'type': 'excalidraw',
        'version': 2,
        'source': 'lib.bin.extraction_dag_excalidraw',
        'elements': elements,
        'appState': {'gridSize': None, 'viewBackgroundColor': '#ffffff'},
        'files': {},
    }


def render() -> str:
    return json.dumps(build(), indent=2) + '\n'


if __name__ == '__main__':
    sys.stdout.write(render())
