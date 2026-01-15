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
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from lib.api.db import get_engine, get_session
from lib.evagg.pdf.thumbnail import pdf_first_page_to_thumbnail_pymupdf_bytes
from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env
from lib.models import Base, ExtractionStatus, PaperDB, PaperResp, CurationDB


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    engine = get_engine()
    session = get_session()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title='PDF Extracting Jobs API', lifespan=lifespan)


# Static File Handling
app.mount(
    env.CUR_AI_SS_ROOT,  # URL path
    StaticFiles(directory=env.CUR_AI_SS_ROOT, html=False),
    name='cur-ai-ss',
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Local Streamlit
        'http://localhost:8501'
    ],
    allow_credentials=True,  # Allows cookies to be sent cross-origin
    allow_methods=['*'],  # Allows all HTTP methods (GET, POST, PUT, etc.)
    allow_headers=['*'],  # Allows all headers
)


@app.middleware('http')
async def log_exceptions_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    try:
        response = await call_next(request)
        # Optionally log 5xx responses
        if 500 <= response.status_code < 600:
            print(
                f'Server error: {request.method} {request.url} returned {response.status_code}'
            )
        return response
    except Exception as e:
        # Log the traceback
        tb = traceback.format_exc()
        print(f'Unhandled exception: {request.method} {request.url}\n{tb}')
        # Return generic 500 response
        return JSONResponse(
            status_code=500,
            content={'detail': 'Internal server error'},
        )


@app.get('/status', tags=['health'])
def get_status() -> dict[str, str]:
    return {'status': 'ok'}


@app.put('/papers', response_model=PaperResp, status_code=status.HTTP_201_CREATED)
def put_paper(
    gene_symbol: str = Form(...),
    uploaded_file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Any:
    if uploaded_file.content_type != 'application/pdf':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Only PDF files are allowed'
        )
    content = uploaded_file.file.read()
    paper = Paper.from_content(content)
    paper_db = session.get(PaperDB, paper.id)
    if paper_db:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Paper extraction already {paper_db.extraction_status.value.lower()}',
        )

    # Add gene symbol to curations table if not yet exist
    curation = session.get(CurationDB, gene_symbol)
    if not curation:
        curation = CurationDB(gene_symbol=gene_symbol)
        session.add(curation)

    else:
        paper.pdf_raw_path.parent.mkdir(parents=True, exist_ok=True)
        with open(paper.pdf_raw_path, 'wb') as f:
            f.write(content)
        with open(paper.pdf_thumbnail_path, 'wb') as fp:
            fp.write(pdf_first_page_to_thumbnail_pymupdf_bytes(content))
        paper_db = PaperDB(
            id=paper.id,
            gene_symbol=gene_symbol,
            filename=uploaded_file.filename,
            extraction_status=ExtractionStatus.QUEUED,
        )
        session.add(paper_db)
    session.refresh(paper_db)
    return paper_db


@app.get('/papers/{paper_id}', response_model=PaperResp)
def get_paper(paper_id: str, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
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


@app.patch('/papers/{paper_id}', response_model=PaperResp)
def update_status(
    paper_id: str,
    extraction_status: ExtractionStatus = Body(..., embed=True),
    session: Session = Depends(get_session),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    if paper_db.extraction_status == extraction_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Status is already {extraction_status.value}',
        )
    paper_db.extraction_status = extraction_status
    session.refresh(paper_db)
    return paper_db


@app.get('/papers', response_model=list[PaperResp])
def list_papers(
    extraction_status: ExtractionStatus | None = None,
    session: Session = Depends(get_session),
) -> Any:
    query = session.query(PaperDB)
    if extraction_status is not None:
        query = query.filter(PaperDB.extraction_status == extraction_status)
    return query.all()
