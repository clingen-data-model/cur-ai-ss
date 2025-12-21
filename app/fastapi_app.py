from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.db import env, get_engine, get_session
from app.models import Base, ExtractionStatus, Paper, PaperDB, PaperExtractionRequest
from lib.evagg.utils.environment import env


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    session = get_session()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title='PDF Extracting Jobs API', lifespan=lifespan)


@app.put('/papers', response_model=Paper)
def queue_extraction(
    req: PaperExtractionRequest, session: Session = Depends(get_session)
):
    paper = session.get(PaperDB, req.id)
    if paper:
        if paper.status == ExtractionStatus.EXTRACTED:
            raise HTTPException(
                status_code=404, detail='Paper extraction already successful'
            )
        if paper.status == ExtractionStatus.QUEUED:
            raise HTTPException(
                status_code=404, detail='Paper extraction already running'
            )
    if not paper:
        paper = PaperDB(id=req.id)
        session.add(paper)
    session.commit()
    session.refresh(paper)
    return paper


@app.get('/papers/{paper_id}', response_model=Paper)
def get_paper(paper_id: str, session: Session = Depends(get_session)):
    paper = session.get(PaperDB, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail='Paper not found')
    return paper


@app.get('/papers', response_model=list[Paper])
def list_jobs(
    status: ExtractionStatus | None = None,
    session: Session = Depends(get_session),
):
    query = session.query(PaperDB)
    if status:
        query = query.filter(PaperDB.status == status)
    return query.all()
