"""POST /papers/{id}/markdown-annotation: the SPA's Markdown evidence tab.

Covers reading the paper's own raw.md by default, and its supplement's raw.md
(a separate file -- see pdf_markdown_path(supplement=...)) when evidence is
tagged is_supplement, which the endpoint did not support until now.
"""

import pytest

from lib.misc.pdf.paths import pdf_dir, pdf_markdown_path, pdf_supplements_dir
from lib.models import GeneDB, PaperDB


@pytest.fixture
def paper_with_markdown(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        gene_id=gene.id, filename='p.pdf', content_hash='h', title='A paper'
    )
    db_session.add(paper)
    db_session.commit()

    pdf_dir(paper.id).mkdir(parents=True, exist_ok=True)
    pdf_markdown_path(paper.id).write_text('# Main\n\nMain paper text.')
    return paper


def test_returns_main_markdown_by_default(client, paper_with_markdown):
    response = client.post(
        f'/papers/{paper_with_markdown.id}/markdown-annotation', json={}
    )
    assert response.status_code == 200
    assert response.json()['content'] == '# Main\n\nMain paper text.'


def test_returns_supplement_markdown_when_requested(client, paper_with_markdown):
    pdf_supplements_dir(paper_with_markdown.id).mkdir(parents=True, exist_ok=True)
    pdf_markdown_path(paper_with_markdown.id, supplement=True).write_text(
        '# Supplement\n\nSupplement text.'
    )

    response = client.post(
        f'/papers/{paper_with_markdown.id}/markdown-annotation',
        json={'is_supplement': True},
    )
    assert response.status_code == 200
    assert response.json()['content'] == '# Supplement\n\nSupplement text.'


def test_404s_when_supplement_markdown_is_missing(client, paper_with_markdown):
    response = client.post(
        f'/papers/{paper_with_markdown.id}/markdown-annotation',
        json={'is_supplement': True},
    )
    assert response.status_code == 404
