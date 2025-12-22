import traceback
from contextlib import asynccontextmanager
from pathlib import Path

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
from sqlalchemy.orm import Session

from app.db import env, get_engine, get_session
from app.models import Base, ExtractionStatus, PaperDB, PaperResp
from lib.evagg.pdf.thumbnail import pdf_first_page_to_thumbnail_pymupdf_bytes
from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    session = get_session()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title='PDF Extracting Jobs API', lifespan=lifespan)


# Static File Handling
app.mount(
    '/var/cur-ai-ss',  # URL path
    StaticFiles(directory='/var/cur-ai-ss', html=False),
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
async def log_exceptions_middleware(request: Request, call_next):
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


@app.put('/papers', response_model=PaperResp)
def queue_extraction(
    uploaded_file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> PaperResp:
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
    else:
        paper.pdf_raw_path.parent.mkdir(parents=True, exist_ok=True)
        with open(paper.pdf_raw_path, 'wb') as f:
            f.write(content)
        with open(paper.pdf_thumbnail_path, 'wb') as fp:
            fp.write(pdf_first_page_to_thumbnail_pymupdf_bytes(content))
        paper_db = PaperDB(
            id=paper.id,
            filename=uploaded_file.filename,
            extraction_status=ExtractionStatus.QUEUED,
        )
        session.add(paper_db)
    session.commit()
    session.refresh(paper_db)
    paper = Paper(id=paper_db.id, content=b'') # TODO: cleaner conversion from PaperDB to Paper
    return PaperResp(
        id=paper_db.id,
        filename=paper_db.filename,
        extraction_status=paper_db.extraction_status,
        raw_path=str(
            paper.pdf_raw_path,
        ),
        thumbnail_path=str(
            paper.pdf_thumbnail_path
        ),
    )


@app.get('/papers/{paper_id}', response_model=PaperResp)
def get_paper(paper_id: str, session: Session = Depends(get_session)) -> PaperResp:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    paper = Paper(id=paper_db.id, content=b'') # TODO: cleaner conversion from PaperDB to Paper
    return PaperResp(
        id=paper_db.id,
        filename=paper_db.filename,
        extraction_status=paper_db.extraction_status,
        raw_path=str(
            paper.pdf_raw_path,
        ),
        thumbnail_path=str(
            paper.pdf_thumbnail_path
        ),
    )


@app.patch('/papers/{paper_id}', response_model=PaperResp)
def update_status(
    paper_id: str,
    extraction_status: ExtractionStatus = Body(..., embed=True),
    session: Session = Depends(get_session),
):
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    if paper_db.extraction_status == extraction_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f'Status is already {extraction_status.value}'
        )
    paper_db.extraction_status = extraction_status
    session.commit()
    session.refresh(paper_db)
    paper = Paper(id=paper_db.id, content=b'') # TODO: cleaner conversion from PaperDB to Paper
    return PaperResp(
        id=paper_db.id,
        filename=paper_db.filename,
        extraction_status=paper_db.extraction_status,
        raw_path=str(
            paper.pdf_raw_path,
        ),
        thumbnail_path=str(
            paper.pdf_thumbnail_path
        ),
    )


@app.get('/papers', response_model=list[PaperResp])
def list_papers(
    extraction_status: ExtractionStatus | None = None,
    session: Session = Depends(get_session),
) -> list[PaperResp]:
    query = session.query(PaperDB)
    if extraction_status:
        query = query.filter(PaperDB.extraction_status == extraction_status)
    paper_dbs = query.all()
    papers = [Paper(id=paper_db.id, content=b'') for paper_db in paper_dbs] # TODO: cleaner conversion from PaperDB to Paper
    return [
        PaperResp(
            id=paper_db.id,
            filename=paper_db.filename,
            extraction_status=paper_db.extraction_status,
            raw_path=str(
                paper.pdf_raw_path,
            ),
            thumbnail_path=str(
                paper.pdf_thumbnail_path
            ),  
        )
        for paper, paper_db in zip(papers, paper_dbs)
    ]
