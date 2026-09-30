"""GET /papers/{id}/document and POST /papers/{id}/highlight: the SPA's evidence
sheet for evidence that cites anchors (slice 3 of docs/evidence-anchors-plan.md).

The legacy pair (/markdown-annotation, /grobid-annotation) stays for evidence
that predates citations; see test_markdown_annotation.py.
"""

import json

import fitz
import pytest

from lib.misc.pdf.anchors import Anchor, PageBox, write_anchored
from lib.misc.pdf.paths import (
    document_anchored_md_path,
    document_raw_path,
    document_words_json_path,
)
from lib.models import GeneDB, PaperDB

PAGE_HEIGHT = 800.0


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        gene_id=gene.id, filename='p.pdf', content_hash='h', title='A paper'
    )
    db_session.add(paper)
    db_session.commit()
    return paper


@pytest.fixture
def document(paper):
    """anchored.md + anchors.json + a one-page raw.pdf + words.json, as parsing leaves them."""
    write_anchored(
        paper.id,
        '## Results\n\n[paragraph-1] Hello world\n',
        [
            Anchor(
                id='paragraph-1',
                boxes=[PageBox(page_no=1, x=10, y=680, width=190, height=20)],
            )
        ],
    )
    pdf = fitz.open()
    pdf.new_page(width=600, height=PAGE_HEIGHT)
    pdf.save(document_raw_path(paper.id))
    document_words_json_path(paper.id).write_text(json.dumps([]))
    return paper


def test_document_returns_the_main_text(client, document):
    response = client.get(f'/papers/{document.id}/document')

    assert response.status_code == 200
    assert response.json() == {
        'main': '## Results\n\n[paragraph-1] Hello world\n',
        'supplement': None,
    }


def test_document_includes_the_supplement_when_present(client, document):
    path = document_anchored_md_path(document.id, supplement=True)
    path.parent.mkdir(parents=True)
    path.write_text('[supp-paragraph-0] Extra\n')

    response = client.get(f'/papers/{document.id}/document')

    assert response.status_code == 200
    assert response.json()['supplement'] == '[supp-paragraph-0] Extra\n'


def test_document_404s_without_a_paper_or_a_document(client, paper):
    assert client.get('/papers/999/document').status_code == 404
    response = client.get(f'/papers/{paper.id}/document')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Document not yet available for this paper'


def test_highlight_resolves_a_paragraph_to_its_box(client, document):
    response = client.post(
        f'/papers/{document.id}/highlight',
        json={
            'citations': [{'anchor': 'paragraph-1', 'quote': ''}],
            'color': '#FF0000',
        },
    )

    assert response.status_code == 200
    # Top-left origin on an unrotated page: y = page height - (y + height).
    assert response.json() == [
        {
            'page': 1,
            'x': 10.0,
            'y': PAGE_HEIGHT - 700,
            'width': 190.0,
            'height': 20.0,
            'color': 'rgb(255.0,0.0,0.0)',
            'border': 'solid',
        }
    ]


def test_highlight_is_empty_for_anchors_without_boxes(client, document):
    response = client.post(
        f'/papers/{document.id}/highlight',
        json={
            'citations': [
                {'anchor': 'supp-paragraph-0'},  # the supplement has no PDF view
                {'anchor': 'paragraph-99'},  # not in this document
                {'anchor': 'figure-0'},  # nor this
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_highlight_validates_paper_color_and_document(client, paper, document):
    assert (
        client.post('/papers/999/highlight', json={'citations': []}).status_code == 404
    )
    assert (
        client.post(
            f'/papers/{document.id}/highlight',
            json={'citations': [], 'color': 'yellow'},
        ).status_code
        == 400
    )
    assert (
        client.post(f'/papers/{document.id}/highlight', json={'citations': []}).json()
        == []
    )


def test_highlight_404s_without_a_document(client, paper):
    response = client.post(
        f'/papers/{paper.id}/highlight',
        json={'citations': [{'anchor': 'paragraph-1'}]},
    )

    assert response.status_code == 404
    assert response.json()['detail'] == 'Document not yet available for this paper'
