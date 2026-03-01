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
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from lib.api.db import get_engine, get_session
from lib.evagg.pdf.thumbnail import pdf_first_page_to_thumbnail_pymupdf_bytes
from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env
from lib.models import (
    Base,
    GeneDB,
    GeneResp,
    PaperDB,
    PaperResp,
    PipelineStatus,
    PipelineUpdateRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    engine = get_engine()
    session = get_session()
    Base.metadata.create_all(bind=engine)
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

    gene = session.execute(
        select(GeneDB).where(GeneDB.symbol == gene_symbol)
    ).scalar_one_or_none()
    if not gene:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f'Gene {gene} not found'
        )

    content = uploaded_file.file.read()
    paper = Paper.from_content(content)
    paper_db = (
        session.query(PaperDB)
        .options(selectinload(PaperDB.gene))
        .filter(PaperDB.id == paper.id)
        .one_or_none()
    )
    if paper_db:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Paper extraction already {paper_db.pipeline_status.value.lower()}',
        )
    else:
        paper.pdf_raw_path.parent.mkdir(parents=True, exist_ok=True)
        with open(paper.pdf_raw_path, 'wb') as f:
            f.write(content)
        with open(paper.pdf_thumbnail_path, 'wb') as fp:
            fp.write(pdf_first_page_to_thumbnail_pymupdf_bytes(content))
        paper_db = PaperDB(
            id=paper.id,
            filename=uploaded_file.filename,
            pipeline_status=PipelineStatus.QUEUED,
        )
        paper_db.gene = gene
        session.add(paper_db)
        session.flush()
    return paper_db


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
    request: PipelineUpdateRequest,
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
    if paper_db.pipeline_status == request.pipeline_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Status is already {request.pipeline_status.value}',
        )
    paper_db.pipeline_status = request.pipeline_status
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


@app.get('/genes', response_model=list[GeneResp])
def list_genes(
    session: Session = Depends(get_session),
) -> Any:
    query = session.query(GeneDB)
    return query.all()
