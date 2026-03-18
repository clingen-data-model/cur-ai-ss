import asyncio
import json
import logging
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from lib.api.db import get_session
from lib.api.middleware import make_log_request_middleware
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.highlight import (
    GrobidAnnotation,
    find_best_match,
    highlight_images_in_pdf,
    highlight_words_in_pdf,
    images_to_grobid_annotations,
    parse_hex_color,
    words_to_grobid_annotations,
)
from lib.misc.pdf.misc import merge_pdfs, pdf_first_page_to_thumbnail_pymupdf_bytes
from lib.misc.pdf.parse import WordLoc
from lib.misc.pdf.paths import (
    pdf_highlighted_path,
    pdf_raw_path,
    pdf_thumbnail_path,
    pdf_words_json_path,
)
from lib.models import (
    GeneDB,
    GeneResp,
    HighlightRequest,
    PaperDB,
    PaperResp,
    PaperUpdateRequest,
    PatientDB,
    PatientResp,
    PipelineStatus,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config('alembic.ini')
    await asyncio.to_thread(command.upgrade, alembic_cfg, 'head')

    setup_logging()  # NB: run setup logging after the alembic setup to prevent it from overriding.
    yield


app = FastAPI(title='PDF Extracting Jobs API', lifespan=lifespan)

# Static File Handling
app.mount(
    env.CAA_ROOT,  # URL path
    StaticFiles(directory=env.CAA_ROOT, html=False),
    name='caa',
)
# Parse CORS origins from env (comma-separated)
_cors_origins = [
    origin.strip() for origin in env.CORS_ALLOWED_ORIGINS.split(',') if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,  # Allows cookies to be sent cross-origin
    allow_methods=['*'],  # Allows all HTTP methods (GET, POST, PUT, etc.)
    allow_headers=['*'],  # Allows all headers
)
app.middleware('http')(make_log_request_middleware(logger))  # Logging middleware


@app.get('/status', tags=['health'])
def get_status() -> dict[str, str]:
    return {'status': 'ok'}


@app.put('/papers', response_model=PaperResp, status_code=status.HTTP_201_CREATED)
def put_paper(
    gene_symbol: str = Form(...),
    uploaded_file: UploadFile = File(...),
    supplement_file: UploadFile | None = File(None),
    session: Session = Depends(get_session),
) -> Any:
    if uploaded_file.content_type != 'application/pdf':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Only PDF files are allowed'
        )
    if supplement_file and supplement_file.content_type != 'application/pdf':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only PDF files are allowed for supplements',
        )
    gene = session.execute(
        select(GeneDB).where(GeneDB.symbol == gene_symbol)
    ).scalar_one_or_none()
    if not gene:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Gene {gene_symbol} not found',
        )
    main_content = uploaded_file.file.read()

    # Merge with supplement if provided
    if supplement_file:
        supplement_content = supplement_file.file.read()
        content = merge_pdfs(main_content, supplement_content)
    else:
        content = main_content

    paper_db = PaperDB.from_content(content)
    paper_db.gene_id = gene.id
    paper_db.filename = uploaded_file.filename or ''
    paper_db.pipeline_status = PipelineStatus.QUEUED
    session.add(paper_db)
    try:
        session.flush()
        pdf_raw_path(paper_db.id).parent.mkdir(parents=True, exist_ok=True)
        with open(pdf_raw_path(paper_db.id), 'wb') as f:
            f.write(content)
        with open(pdf_highlighted_path(paper_db.id), 'wb') as f:
            f.write(content)
        with open(pdf_thumbnail_path(paper_db.id), 'wb') as fp:
            fp.write(pdf_first_page_to_thumbnail_pymupdf_bytes(content))
        return paper_db
    except IntegrityError:
        session.rollback()
        existing = (
            session.query(PaperDB)
            .options(selectinload(PaperDB.gene))
            .filter(PaperDB.id == paper_db.id)
            .one()
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Paper extraction already {existing.pipeline_status.value.lower()}',
        )


@app.get('/papers/{paper_id}', response_model=PaperResp)
def get_paper(paper_id: str, session: Session = Depends(get_session)) -> Any:
    paper_db = (
        session.query(PaperDB)
        .options(selectinload(PaperDB.gene))
        .filter(PaperDB.id == paper_id)
        .one_or_none()
    )
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    return paper_db


@app.delete('/papers/{paper_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(paper_id: str, session: Session = Depends(get_session)) -> None:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        return
    session.delete(paper_db)
    session.flush()


@app.patch('/papers/{paper_id}', response_model=PaperResp)
def update_status(
    paper_id: str,
    patch_request: PaperUpdateRequest,
    session: Session = Depends(get_session),
) -> Any:
    paper_db = (
        session.query(PaperDB)
        .options(selectinload(PaperDB.gene))
        .filter(PaperDB.id == paper_id)
        .one_or_none()
    )

    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    if paper_db.pipeline_status == patch_request.pipeline_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Status is already {patch_request.pipeline_status.value}',
        )
    patch_request.apply_to(paper_db)
    return paper_db


@app.get('/papers', response_model=list[PaperResp])
def list_papers(
    pipeline_status: PipelineStatus | None = None,
    session: Session = Depends(get_session),
) -> Any:
    query = session.query(PaperDB).options(selectinload(PaperDB.gene))

    if pipeline_status is not None:
        query = query.filter(PaperDB.pipeline_status == pipeline_status)
    return query.all()


@app.get('/papers/{paper_id}/patients', response_model=list[PatientResp])
def get_patients(paper_id: str, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patients = (
        session.query(PatientDB)
        .filter(PatientDB.paper_id == paper_id)
        .order_by(PatientDB.patient_idx)
        .all()
    )
    return patients


@app.get('/genes/search', response_model=list[GeneResp])
def search_genes(
    prefix: str = Query(...),
    limit: int = Query(10),
    session: Session = Depends(get_session),
) -> Any:
    query = (
        session.query(GeneDB)
        .filter(GeneDB.symbol.startswith(prefix))
        .order_by(GeneDB.symbol)
        .limit(limit)
    )
    return query.all()


@app.get('/genes', response_model=list[GeneResp])
def list_genes(
    limit: int = Query(10),
    session: Session = Depends(get_session),
) -> Any:
    query = session.query(GeneDB).order_by(GeneDB.symbol).limit(limit)
    return query.all()


@app.post('/papers/{paper_id}/highlight', status_code=status.HTTP_204_NO_CONTENT)
def highlight_pdf(
    paper_id: str,
    request: HighlightRequest,
    session: Session = Depends(get_session),
) -> None:
    """
    Highlight text in a PDF and save the highlighted version.

    Args:
        paper_id: The ID of the paper
        request: JSON body with queries (list) and color fields
    """
    # Verify paper exists
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    # Parse and validate color
    try:
        rgb_color = parse_hex_color(request.color)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Load words from JSON file
    words_file = pdf_words_json_path(paper_id)
    with open(words_file, 'r') as f:
        words = json.load(f)
        words = [WordLoc(**word) for word in words]

    # Process each query
    for query in request.queries:
        # Find best match for the query in the PDF
        matched_words = find_best_match(query, words)
        if not matched_words:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Could not find text matching query: "{query}"',
            )

        # Highlight the matched words in the PDF
        highlight_words_in_pdf(paper_id, matched_words, rgb_color)

    # Also highlight requested images
    highlight_images_in_pdf(
        paper_id,
        request.image_ids,
        rgb_color,
    )


@app.post('/papers/{paper_id}/grobid-annotation', response_model=list[GrobidAnnotation])
def grobid_annotation(
    paper_id: str,
    request: HighlightRequest,
    session: Session = Depends(get_session),
) -> list[GrobidAnnotation]:
    """
    Find best text matches and return their coordinates in GROBID format.

    Args:
        paper_id: The ID of the paper
        request: JSON body with queries (list) and color fields

    Returns:
        List of GROBID-style coordinates for all matched text
    """
    # Verify paper exists
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    # Parse and validate color
    try:
        rgb_color = parse_hex_color(request.color)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Load words from JSON file
    words_file = pdf_words_json_path(paper_id)
    with open(words_file, 'r') as f:
        words = json.load(f)
        words = [WordLoc(**word) for word in words]

    # Find matches for all queries and collect annotations
    all_annotations: list[GrobidAnnotation] = []
    for query in request.queries:
        matched_words = find_best_match(query, words)
        if not matched_words:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Could not find text matching query: "{query}"',
            )

        # Convert to GROBID annotations
        annotations = words_to_grobid_annotations(
            paper_id,
            matched_words,
            rgb_color,
        )
        all_annotations.extend(annotations)

    all_annotations.extend(
        images_to_grobid_annotations(
            paper_id,
            request.image_ids,
            rgb_color,
        )
    )

    return all_annotations


@app.post('/papers/{paper_id}/clear-highlights', status_code=status.HTTP_204_NO_CONTENT)
def clear_highlights(
    paper_id: str,
    session: Session = Depends(get_session),
) -> None:
    """
    Clear all highlights from a paper by replacing the highlighted PDF with the raw PDF.

    Args:
        paper_id: The ID of the paper
    """
    # Verify paper exists
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    raw_path = pdf_raw_path(paper_id)
    highlighted_path = pdf_highlighted_path(paper_id)

    with open(raw_path, 'rb') as f:
        content = f.read()
    with open(highlighted_path, 'wb') as f:
        f.write(content)
