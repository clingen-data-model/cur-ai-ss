import asyncio
import json
import logging
import shutil
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from agents import Runner
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
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from lib.agents.chat_routing_agent import (
    _GLOBAL_AGENTS,
    CHAT_ROUTING_INSTRUCTIONS,
    ChatRoutingOutput,
    make_routing_agent,
)
from lib.agents.general_paper_qa_agent import (
    GENERAL_PAPER_QA_INSTRUCTIONS,
)
from lib.agents.general_paper_qa_agent import (
    agent as general_paper_qa_agent,
)
from lib.agents.run_tracking import ensure_agent_run
from lib.api.db import get_session, session_scope
from lib.api.middleware import make_log_request_middleware
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.curation.models import CurationSummaryRow
from lib.misc.curation.pptx import build_curation_pptx
from lib.misc.curation.summary import build_curation_row
from lib.misc.pdf.highlight import (
    GrobidAnnotation,
    figures_to_grobid_annotations,
    find_best_match,
    highlight_figures_in_pdf,
    highlight_words_in_pdf,
    parse_hex_color,
    words_to_grobid_annotations,
)
from lib.misc.pdf.misc import (
    pdf_first_page_to_thumbnail_pymupdf_bytes,
)
from lib.misc.pdf.parse import WordLoc
from lib.misc.pdf.paths import (
    pdf_dir,
    pdf_highlighted_path,
    pdf_raw_path,
    pdf_supplements_dir,
    pdf_thumbnail_path,
    pdf_words_json_path,
    relevant_sections_md,
)
from lib.models import (
    AgentRunDB,
    AnnotatedVariantDB,
    AnnotatedVariantResp,
    ChatMessageRequest,
    ChatMessageResp,
    ChatRoutingResponse,
    ConversationDB,
    ExtractedPhenotype,
    FamilyCreateRequest,
    FamilyDB,
    FamilyResp,
    FamilyUpdateRequest,
    FileFormat,
    GeneDB,
    GeneResp,
    HarmonizedVariantDB,
    HarmonizedVariantResp,
    HighlightRequest,
    HpoDB,
    HPOTerm,
    HumanEvidenceBlock,
    PaperDB,
    PaperResp,
    PaperUpdateRequest,
    PatientCreateRequest,
    PatientDB,
    PatientResp,
    PatientUpdateRequest,
    PatientVariantOccurrenceDB,
    PatientVariantOccurrenceResp,
    PedigreeDB,
    PedigreeResp,
    PhenotypeDB,
    PhenotypeResp,
    PhenotypeUpdateRequest,
    SegregationAnalysisComputedDB,
    SegregationAnalysisResp,
    SegregationEvidenceDB,
    TaskDB,
    VariantDB,
    VariantResp,
    VariantUpdateRequest,
)
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.segregation_analysis import SegregationAnalysisComputedNestedResp
from lib.tasks import TaskCreateRequest, TaskResp, enqueue_all_instances, enqueue_task
from lib.tasks.handlers import ensure_conversation_id
from lib.tasks.models import TaskStatus, TaskType

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


@app.middleware('http')
async def add_cache_headers(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    response = await call_next(request)
    # Add 24-hour cache headers for static files (thumbnails, PDFs, etc.)
    if request.url.path.startswith(f'/{env.CAA_ROOT}'):
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 24 hours
    return response


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
    valid_supplement_types = {
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }
    if supplement_file and supplement_file.content_type not in valid_supplement_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only PDF, DOCX, or XLSX files are allowed for supplements',
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

    # Ensure agent run exists
    latest_run = session.query(AgentRunDB).order_by(AgentRunDB.id.desc()).first()
    if not latest_run:
        latest_run = ensure_agent_run(
            session=session,
            description='Web UI upload',
            model=env.OPENAI_API_DEPLOYMENT,
        )

    paper_db = PaperDB.from_content(main_content)
    paper_db.gene_id = gene.id
    paper_db.filename = uploaded_file.filename or ''
    session.add(paper_db)
    try:
        # Create initial PDF_PARSING task
        task = TaskDB(
            paper_id=paper_db.id,
            agent_run_id=latest_run.id,
            type=TaskType.PDF_PARSING,
            status=TaskStatus.PENDING,
        )
        paper_db.tasks.append(task)
        session.flush()

        pdf_raw_path(paper_db.id).parent.mkdir(parents=True, exist_ok=True)
        with open(pdf_raw_path(paper_db.id), 'wb') as f:
            f.write(main_content)
        with open(pdf_highlighted_path(paper_db.id), 'wb') as f:
            f.write(main_content)
        with open(pdf_thumbnail_path(paper_db.id), 'wb') as fp:
            fp.write(pdf_first_page_to_thumbnail_pymupdf_bytes(main_content))

        if supplement_file:
            pdf_supplements_dir(paper_db.id).mkdir(parents=True, exist_ok=True)
            supplement_content = supplement_file.file.read()
            if (
                supplement_file.content_type
                == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ):
                paper_db.supplement_format = FileFormat.DOCX
            elif (
                supplement_file.content_type
                == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ):
                paper_db.supplement_format = FileFormat.XLSX
            else:
                paper_db.supplement_format = FileFormat.PDF
            with open(
                pdf_raw_path(
                    paper_db.id,
                    supplement=True,
                    file_format=paper_db.supplement_format.value,
                ),
                'wb',
            ) as f:
                f.write(supplement_content)
        return paper_db
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Paper with this content already exists',
        )


@app.get('/papers/{paper_id}', response_model=PaperResp)
def get_paper(paper_id: int, session: Session = Depends(get_session)) -> Any:
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
def delete_paper(paper_id: int, session: Session = Depends(get_session)) -> None:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        return

    # Delete extracted PDF directory
    pdf_directory = pdf_dir(paper_id)
    if pdf_directory.exists():
        shutil.rmtree(pdf_directory)

    session.delete(paper_db)
    session.flush()


@app.patch('/papers/{paper_id}', response_model=PaperResp)
def update_paper(
    paper_id: int,
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
    patch_request.apply_to(paper_db)
    return paper_db


@app.get('/papers', response_model=list[PaperResp])
def list_papers(
    session: Session = Depends(get_session),
) -> Any:
    query = session.query(PaperDB).options(
        selectinload(PaperDB.gene),
        selectinload(PaperDB.tasks),
        selectinload(PaperDB.patients),
        selectinload(PaperDB.variants),
    )
    papers = query.all()
    for paper in papers:
        paper.patient_count = len(paper.patients)
        paper.variant_count = len(paper.variants)
    return papers


@app.get('/papers/{paper_id}/tasks', response_model=list[TaskResp])
def list_tasks(
    paper_id: int,
    session: Session = Depends(get_session),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    tasks = (
        session.query(TaskDB)
        .filter(TaskDB.paper_id == paper_id)
        .order_by(TaskDB.id)
        .all()
    )
    return tasks


@app.post('/papers/{paper_id}/tasks', response_model=list[TaskResp])
def create_task(
    paper_id: int,
    request: TaskCreateRequest,
    session: Session = Depends(get_session),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    if (
        request.family_id is None
        and request.patient_id is None
        and request.variant_id is None
        and request.phenotype_id is None
    ):
        tasks = enqueue_all_instances(
            session,
            paper_id=paper_id,
            task_type=request.type,
            skip_successors=request.skip_successors,
            additional_context=request.additional_context,
        )
    else:
        task = enqueue_task(
            session,
            paper_id=paper_id,
            task_type=request.type,
            family_id=request.family_id,
            patient_id=request.patient_id,
            variant_id=request.variant_id,
            phenotype_id=request.phenotype_id,
            skip_successors=request.skip_successors,
            additional_context=request.additional_context,
        )
        tasks = [task]
    return tasks


def _patient_to_resp(row: PatientDB) -> PatientResp:
    return PatientResp(
        id=row.id,
        paper_id=row.paper_id,
        identifier=row.identifier,
        identifier_evidence=HumanEvidenceBlock.model_validate(row.identifier_evidence),
        proband_status=row.proband_status,
        proband_status_evidence=HumanEvidenceBlock.model_validate(
            row.proband_status_evidence
        ),
        sex=row.sex,
        sex_evidence=HumanEvidenceBlock.model_validate(row.sex_evidence),
        age_diagnosis=row.age_diagnosis,
        age_diagnosis_unit=row.age_diagnosis_unit,
        age_diagnosis_evidence=HumanEvidenceBlock.model_validate(
            row.age_diagnosis_evidence
        ),
        age_report=row.age_report,
        age_report_unit=row.age_report_unit,
        age_report_evidence=HumanEvidenceBlock.model_validate(row.age_report_evidence),
        age_death=row.age_death,
        age_death_unit=row.age_death_unit,
        age_death_evidence=HumanEvidenceBlock.model_validate(row.age_death_evidence),
        country_of_origin=row.country_of_origin,
        country_of_origin_evidence=HumanEvidenceBlock.model_validate(
            row.country_of_origin_evidence
        ),
        race_ethnicity=row.race_ethnicity,
        race_ethnicity_evidence=HumanEvidenceBlock.model_validate(
            row.race_ethnicity_evidence
        ),
        affected_status=row.affected_status,
        affected_status_evidence=HumanEvidenceBlock.model_validate(
            row.affected_status_evidence
        ),
        is_obligate_carrier=row.is_obligate_carrier,
        relationship_to_proband=row.relationship_to_proband,
        twin_type=row.twin_type,
        is_obligate_carrier_evidence=HumanEvidenceBlock.model_validate(
            row.is_obligate_carrier_evidence
        ),
        relationship_to_proband_evidence=HumanEvidenceBlock.model_validate(
            row.relationship_to_proband_evidence
        ),
        twin_type_evidence=HumanEvidenceBlock.model_validate(row.twin_type_evidence),
        updated_at=row.updated_at,
        family_id=row.family.id,
        family_identifier=row.family.identifier,
        family_assignment_evidence=HumanEvidenceBlock.model_validate(
            row.family_assignment_evidence
        ),
    )


@app.get('/papers/{paper_id}/patients', response_model=list[PatientResp])
def get_patients(paper_id: int, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patients = (
        session.query(PatientDB)
        .options(selectinload(PatientDB.family))
        .filter(PatientDB.paper_id == paper_id)
        .order_by(PatientDB.id)
        .all()
    )
    return [_patient_to_resp(p) for p in patients]


@app.post(
    '/papers/{paper_id}/patients',
    response_model=PatientResp,
    status_code=status.HTTP_201_CREATED,
)
def create_patient(
    paper_id: int,
    patient_data: PatientCreateRequest,
    session: Session = Depends(get_session),
) -> Any:
    from lib.models.evidence_block import EvidenceBlock

    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    family_db = session.get(FamilyDB, patient_data.family_id)
    if not family_db or family_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Family not found'
        )

    def create_evidence_block(value: Any) -> dict:
        """Create an evidence block for human-created data."""
        block = EvidenceBlock(
            value=value,
            reasoning='Created by human',
            quote='Created manually',
        )
        return block.model_dump()

    patient_db = PatientDB(
        paper_id=paper_id,
        family_id=patient_data.family_id,
        identifier=patient_data.identifier,
        identifier_evidence=create_evidence_block(patient_data.identifier),
        proband_status=patient_data.proband_status,
        proband_status_evidence=create_evidence_block(patient_data.proband_status),
        sex=patient_data.sex,
        sex_evidence=create_evidence_block(patient_data.sex),
        age_diagnosis=patient_data.age_diagnosis,
        age_diagnosis_evidence=create_evidence_block(patient_data.age_diagnosis),
        age_report=patient_data.age_report,
        age_report_evidence=create_evidence_block(patient_data.age_report),
        age_death=patient_data.age_death,
        age_death_evidence=create_evidence_block(patient_data.age_death),
        country_of_origin=patient_data.country_of_origin,
        country_of_origin_evidence=create_evidence_block(
            patient_data.country_of_origin
        ),
        race_ethnicity=patient_data.race_ethnicity,
        race_ethnicity_evidence=create_evidence_block(patient_data.race_ethnicity),
        affected_status=patient_data.affected_status,
        affected_status_evidence=create_evidence_block(patient_data.affected_status),
    )
    session.add(patient_db)
    session.flush()
    patient_db = (
        session.query(PatientDB)
        .options(selectinload(PatientDB.family))
        .filter(PatientDB.id == patient_db.id)
        .one()
    )
    return _patient_to_resp(patient_db)


@app.get('/papers/{paper_id}/families', response_model=list[FamilyResp])
def get_families(paper_id: int, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    return (
        session.query(FamilyDB)
        .filter(FamilyDB.paper_id == paper_id)
        .order_by(FamilyDB.id)
        .all()
    )


@app.get('/papers/{paper_id}/pedigree', response_model=PedigreeResp | None)
def get_pedigree(paper_id: int, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    pedigree = (
        session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).one_or_none()
    )
    return pedigree


def _segregation_analysis_to_resp(
    family: FamilyDB,
    evidence: SegregationEvidenceDB,
    computed: SegregationAnalysisComputedDB | None,
) -> SegregationAnalysisResp:
    computed_nested = None
    if computed:
        computed_nested = SegregationAnalysisComputedNestedResp(
            segregation_count=ReasoningBlock.model_validate(
                computed.segregation_count_reasoning
            ),
            affected_count=ReasoningBlock.model_validate(
                computed.affected_count_reasoning
            ),
            unaffected_count=ReasoningBlock.model_validate(
                computed.unaffected_count_reasoning
            ),
            computed_lod_score=ReasoningBlock.model_validate(
                computed.computed_lod_score_reasoning
            ),
            points_assigned=ReasoningBlock.model_validate(
                computed.points_assigned_reasoning
            ),
            meets_minimum_criteria=ReasoningBlock.model_validate(
                computed.meets_minimum_criteria_reasoning
            ),
        )

    return SegregationAnalysisResp(
        id=computed.id if computed else evidence.id,
        family_id=family.id,
        extracted_lod_score=HumanEvidenceBlock.model_validate(
            evidence.extracted_lod_score_evidence or {}
        ),
        has_unexplainable_non_segregations=HumanEvidenceBlock.model_validate(
            evidence.has_unexplainable_non_segregations_evidence or {}
        ),
        computed=computed_nested,
        updated_at=computed.updated_at if computed else evidence.updated_at,
    )


@app.get(
    '/papers/{paper_id}/segregation-analysis',
    response_model=list[SegregationAnalysisResp],
)
def get_segregation_analysis(
    paper_id: int, session: Session = Depends(get_session)
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    # Get all families with their evidence and computed analysis using join
    rows = (
        session.query(FamilyDB, SegregationEvidenceDB, SegregationAnalysisComputedDB)
        .filter(FamilyDB.paper_id == paper_id)
        .join(SegregationEvidenceDB, FamilyDB.id == SegregationEvidenceDB.family_id)
        .outerjoin(
            SegregationAnalysisComputedDB,
            FamilyDB.id == SegregationAnalysisComputedDB.family_id,
        )
        .all()
    )
    result = [
        _segregation_analysis_to_resp(family, evidence, computed)
        for family, evidence, computed in rows
    ]
    return result


@app.get('/papers/{paper_id}/variants', response_model=list[VariantResp])
def get_variants(paper_id: int, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    variants = (
        session.query(VariantDB)
        .options(
            joinedload(VariantDB.harmonized_variant),
            joinedload(VariantDB.annotated_variant),
        )
        .filter(VariantDB.paper_id == paper_id)
        .order_by(VariantDB.id)
        .all()
    )
    return [_variant_to_resp(v) for v in variants]


def _variant_to_resp(row: VariantDB) -> VariantResp:
    """Convert VariantDB to VariantResp, including harmonized and enriched data."""
    hv = row.harmonized_variant
    if hv:
        harmonized = ReasoningBlock[HarmonizedVariantResp | None](
            value=HarmonizedVariantResp(
                gnomad_style_coordinates=hv.gnomad_style_coordinates,
                rsid=hv.rsid,
                caid=hv.caid,
                hgvs_c=hv.hgvs_c,
                hgvs_p=hv.hgvs_p,
                hgvs_g=hv.hgvs_g,
            ),
            reasoning=hv.reasoning,
        )
    else:
        harmonized = ReasoningBlock[HarmonizedVariantResp | None](
            value=None,
            reasoning='Harmonization not yet performed',
        )
    enriched = (
        AnnotatedVariantResp(
            gnomad_style_coordinates=row.annotated_variant.gnomad_style_coordinates,
            rsid=row.annotated_variant.rsid,
            caid=row.annotated_variant.caid,
            pathogenicity=row.annotated_variant.pathogenicity,
            submissions=row.annotated_variant.submissions,
            stars=row.annotated_variant.stars,
            exon=row.annotated_variant.exon,
            revel=row.annotated_variant.revel,
            alphamissense_class=row.annotated_variant.alphamissense_class,
            alphamissense_score=row.annotated_variant.alphamissense_score,
            spliceai=row.annotated_variant.spliceai,
            gnomad_top_level_af=row.annotated_variant.gnomad_top_level_af,
            gnomad_popmax_af=row.annotated_variant.gnomad_popmax_af,
            gnomad_popmax_population=row.annotated_variant.gnomad_popmax_population,
        )
        if row.annotated_variant
        else None
    )
    return VariantResp(
        id=row.id,
        paper_id=row.paper_id,
        variant=row.variant,
        transcript=row.transcript,
        protein_accession=row.protein_accession,
        genomic_accession=row.genomic_accession,
        lrg_accession=row.lrg_accession,
        gene_accession=row.gene_accession,
        genomic_coordinates=row.genomic_coordinates,
        genome_build=row.genome_build,
        rsid=row.rsid,
        caid=row.caid,
        hgvs_c=row.hgvs_c,
        hgvs_p=row.hgvs_p,
        hgvs_g=row.hgvs_g,
        variant_type=row.variant_type,
        functional_evidence=row.functional_evidence,
        updated_at=row.updated_at,
        transcript_evidence=EvidenceBlock.model_validate(row.transcript_evidence),
        protein_accession_evidence=EvidenceBlock.model_validate(
            row.protein_accession_evidence
        ),
        genomic_accession_evidence=EvidenceBlock.model_validate(
            row.genomic_accession_evidence
        ),
        lrg_accession_evidence=EvidenceBlock.model_validate(row.lrg_accession_evidence),
        gene_accession_evidence=EvidenceBlock.model_validate(
            row.gene_accession_evidence
        ),
        genomic_coordinates_evidence=EvidenceBlock.model_validate(
            row.genomic_coordinates_evidence
        ),
        genome_build_evidence=EvidenceBlock.model_validate(row.genome_build_evidence),
        rsid_evidence=EvidenceBlock.model_validate(row.rsid_evidence),
        caid_evidence=EvidenceBlock.model_validate(row.caid_evidence),
        variant_evidence=EvidenceBlock.model_validate(row.variant_evidence),
        hgvs_c_evidence=EvidenceBlock.model_validate(row.hgvs_c_evidence),
        hgvs_p_evidence=EvidenceBlock.model_validate(row.hgvs_p_evidence),
        hgvs_g_evidence=EvidenceBlock.model_validate(row.hgvs_g_evidence),
        variant_type_evidence=HumanEvidenceBlock.model_validate(
            row.variant_type_evidence
        ),
        functional_evidence_evidence=HumanEvidenceBlock.model_validate(
            row.functional_evidence_evidence
        ),
        main_focus=row.main_focus,
        main_focus_evidence=HumanEvidenceBlock.model_validate(row.main_focus_evidence),
        harmonized_variant=harmonized,
        annotated_variant=enriched,
    )


@app.patch('/papers/{paper_id}/variants/{variant_id}', response_model=VariantResp)
def update_variant(
    paper_id: int,
    variant_id: int,
    patch_request: VariantUpdateRequest,
    session: Session = Depends(get_session),
) -> Any:
    variant_db = (
        session.query(VariantDB)
        .options(
            joinedload(VariantDB.harmonized_variant),
            joinedload(VariantDB.annotated_variant),
        )
        .filter(VariantDB.id == variant_id, VariantDB.paper_id == paper_id)
        .one_or_none()
    )
    if not variant_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Variant not found'
        )
    patch_request.apply_to(variant_db)
    # Editing any harmonized field invalidates the downstream enrichment row,
    # which was computed by key lookup from the pre-edit coordinates. Treat
    # all harmonized siblings uniformly so a future enrichment lookup added
    # for e.g. hgvs_p cannot silently produce stale annotations. The
    # LLM-generated reasoning on harmonized_variant is intentionally kept
    # intact: it remains the agent's explanation of its original choices,
    # and the curator's rationale belongs in human_edit_note fields.
    harmonized_update = (
        patch_request.harmonized_variant
        if 'harmonized_variant' in patch_request.model_fields_set
        else None
    )
    if harmonized_update is not None:
        if variant_db.harmonized_variant is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Variant has not been harmonized by the server yet',
            )
        harmonized_update.apply_to(variant_db.harmonized_variant)
        # delete-orphan cascade removes the row
        variant_db.annotated_variant = None
    session.flush()
    return _variant_to_resp(variant_db)


def _phenotype_to_resp(row: PhenotypeDB) -> PhenotypeResp:
    if row.hpo:
        hpo_value = (
            HPOTerm(id=row.hpo.hpo_id, name=row.hpo.hpo_name)
            if row.hpo.hpo_id and row.hpo.hpo_name
            else None
        )
        hpo = ReasoningBlock[HPOTerm | None](
            value=hpo_value,
            reasoning=row.hpo.reasoning,
        )
    else:
        hpo = ReasoningBlock[HPOTerm | None](
            value=None,
            reasoning='HPO linking not yet performed',
        )
    return PhenotypeResp(
        id=row.id,
        paper_id=row.paper_id,
        patient_id=row.patient_id,
        concept=row.concept,
        concept_evidence=EvidenceBlock.model_validate(row.concept_evidence),
        negated=row.negated,
        uncertain=row.uncertain,
        family_history=row.family_history,
        onset=row.onset,
        location=row.location,
        severity=row.severity,
        modifier=row.modifier,
        updated_at=row.updated_at,
        hpo=hpo,
    )


@app.get(
    '/papers/{paper_id}/occurrences',
    response_model=list[PatientVariantOccurrenceResp],
)
def get_occurrences(paper_id: int, session: Session = Depends(get_session)) -> Any:
    """Get all patient-variant occurrences for a paper."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    from lib.models.patient import PatientDB

    links = (
        session.query(PatientVariantOccurrenceDB, PatientDB.identifier)
        .join(PatientDB, PatientVariantOccurrenceDB.patient_id == PatientDB.id)
        .filter(PatientVariantOccurrenceDB.paper_id == paper_id)
        .order_by(
            PatientVariantOccurrenceDB.patient_id, PatientVariantOccurrenceDB.variant_id
        )
        .all()
    )
    return [
        _patient_variant_occurrence_to_resp(link[0], patient_identifier=link[1])
        for link in links
    ]


@app.get(
    '/papers/{paper_id}/variants/{variant_id}/occurrences',
    response_model=list[PatientVariantOccurrenceResp],
)
def get_variant_occurrences(
    paper_id: int, variant_id: int, session: Session = Depends(get_session)
) -> Any:
    """Get all patient occurrences of a specific variant."""
    variant_db = session.get(VariantDB, variant_id)
    if not variant_db or variant_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Variant not found'
        )
    from lib.models.patient import PatientDB

    links = (
        session.query(PatientVariantOccurrenceDB, PatientDB.identifier)
        .join(PatientDB, PatientVariantOccurrenceDB.patient_id == PatientDB.id)
        .filter(
            PatientVariantOccurrenceDB.variant_id == variant_id,
            PatientVariantOccurrenceDB.paper_id == paper_id,
        )
        .order_by(PatientVariantOccurrenceDB.patient_id)
        .all()
    )
    return [
        _patient_variant_occurrence_to_resp(link[0], patient_identifier=link[1])
        for link in links
    ]


@app.get(
    '/papers/{paper_id}/patients/{patient_id}/occurrences',
    response_model=list[PatientVariantOccurrenceResp],
)
def get_patient_occurrences(
    paper_id: int, patient_id: int, session: Session = Depends(get_session)
) -> Any:
    """Get all variant occurrences for a specific patient."""
    patient_db = session.get(PatientDB, patient_id)
    if not patient_db or patient_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    from lib.models.patient import PatientDB

    links = (
        session.query(PatientVariantOccurrenceDB, PatientDB.identifier)
        .join(PatientDB, PatientVariantOccurrenceDB.patient_id == PatientDB.id)
        .filter(
            PatientVariantOccurrenceDB.patient_id == patient_id,
            PatientVariantOccurrenceDB.paper_id == paper_id,
        )
        .order_by(PatientVariantOccurrenceDB.variant_id)
        .all()
    )
    return [
        _patient_variant_occurrence_to_resp(link[0], patient_identifier=link[1])
        for link in links
    ]


def _patient_variant_occurrence_to_resp(
    row: PatientVariantOccurrenceDB,
    patient_identifier: str,
) -> PatientVariantOccurrenceResp:
    """Convert PatientVariantOccurrenceDB to PatientVariantOccurrenceResp."""
    from lib.models import Inheritance, TestingMethod, Zygosity

    return PatientVariantOccurrenceResp(
        id=row.id,
        paper_id=row.paper_id,
        patient_id=row.patient_id,
        patient_identifier=patient_identifier,
        variant_id=row.variant_id,
        zygosity=Zygosity(row.zygosity),
        zygosity_evidence=EvidenceBlock.model_validate(row.zygosity_evidence),
        inheritance=Inheritance(row.inheritance),
        inheritance_evidence=EvidenceBlock.model_validate(row.inheritance_evidence),
        de_novo=row.de_novo,
        de_novo_evidence=EvidenceBlock.model_validate(row.de_novo_evidence),
        testing_methods=[TestingMethod(m) for m in row.testing_methods],
        testing_methods_evidence=[
            EvidenceBlock.model_validate(m) for m in row.testing_methods_evidence
        ],
        disease_name=row.disease_name,
        disease_name_evidence=EvidenceBlock.model_validate(row.disease_name_evidence)
        if row.disease_name_evidence
        else None,
        paired_variant_link_id=row.paired_variant_link_id,
        updated_at=row.updated_at,
    )


@app.get(
    '/papers/{paper_id}/curation-row',
    response_model=CurationSummaryRow,
)
def get_curation_row(paper_id: int, session: Session = Depends(get_session)) -> Any:
    """Get a curation summary row for a single paper."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    try:
        return build_curation_row(paper_id, session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    '/papers/{paper_id}/curation-export',
)
def get_curation_export(
    paper_id: int, session: Session = Depends(get_session)
) -> Response:
    """Export a curation summary as a PPTX file."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    try:
        row = build_curation_row(paper_id, session)
        pptx_bytes = build_curation_pptx([row])
        return Response(
            content=pptx_bytes,
            media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            headers={
                'Content-Disposition': f'attachment; filename="curation_{paper_id}.pptx"'
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    '/papers/{paper_id}/patients/{patient_id}/phenotypes',
    response_model=list[PhenotypeResp],
)
def get_phenotypes(
    paper_id: int, patient_id: int, session: Session = Depends(get_session)
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patient_db = (
        session.query(PatientDB).filter(PatientDB.id == patient_id).one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    phenotypes = (
        session.query(PhenotypeDB)
        .options(joinedload(PhenotypeDB.hpo))
        .filter(
            PhenotypeDB.patient_id == patient_id,
        )
        .order_by(PhenotypeDB.id)
        .all()
    )
    return [_phenotype_to_resp(p) for p in phenotypes]


@app.post(
    '/papers/{paper_id}/patients/{patient_id}/phenotypes',
    response_model=PhenotypeResp,
)
def create_phenotype(
    paper_id: int,
    patient_id: int,
    phenotype_data: ExtractedPhenotype,
    session: Session = Depends(get_session),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patient_db = (
        session.query(PatientDB).filter(PatientDB.id == patient_id).one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )

    phenotype_db = PhenotypeDB(
        paper_id=paper_id,
        patient_id=patient_id,
        concept=phenotype_data.concept.value,
        concept_evidence=phenotype_data.concept.model_dump(),
        negated=phenotype_data.negated,
        uncertain=phenotype_data.uncertain,
        family_history=phenotype_data.family_history,
        onset=phenotype_data.onset,
        location=phenotype_data.location,
        severity=phenotype_data.severity,
        modifier=phenotype_data.modifier,
    )
    session.add(phenotype_db)
    return phenotype_db


@app.patch(
    '/papers/{paper_id}/patients/{patient_id}/phenotypes/{phenotype_id}',
    response_model=PhenotypeResp,
)
def update_phenotype(
    paper_id: int,
    patient_id: int,
    phenotype_id: int,
    patch_request: PhenotypeUpdateRequest,
    session: Session = Depends(get_session),
) -> Any:
    phenotype_db = (
        session.query(PhenotypeDB)
        .options(joinedload(PhenotypeDB.hpo))
        .filter(
            PhenotypeDB.id == phenotype_id,
            PhenotypeDB.paper_id == paper_id,
            PhenotypeDB.patient_id == patient_id,
        )
        .one_or_none()
    )
    if not phenotype_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Phenotype not found'
        )
    patch_request.apply_to(phenotype_db)
    return phenotype_db


@app.patch('/papers/{paper_id}/patients/{patient_id}', response_model=PatientResp)
def update_patient(
    paper_id: int,
    patient_id: int,
    patch_request: PatientUpdateRequest,
    session: Session = Depends(get_session),
) -> Any:
    patient_db = (
        session.query(PatientDB)
        .options(selectinload(PatientDB.family))
        .filter(PatientDB.id == patient_id, PatientDB.paper_id == paper_id)
        .one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    patch_request.apply_to(patient_db)
    return _patient_to_resp(patient_db)


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
    limit: int | None = Query(None),
    session: Session = Depends(get_session),
) -> Any:
    query = session.query(GeneDB).order_by(GeneDB.symbol)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@app.post('/papers/{paper_id}/highlight', status_code=status.HTTP_204_NO_CONTENT)
def highlight_pdf(
    paper_id: int,
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

    # Return early if no highlightable evidence (e.g., all from supplements)
    if not request.queries and not request.image_ids and not request.table_ids:
        return

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

    # Also highlight requested figures
    highlight_figures_in_pdf(
        paper_id,
        request.image_ids,
        request.table_ids,
        rgb_color,
    )


@app.post('/papers/{paper_id}/grobid-annotation', response_model=list[GrobidAnnotation])
def grobid_annotation(
    paper_id: int,
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

    # Return early if no highlightable evidence (e.g., all from supplements)
    if not request.queries and not request.image_ids and not request.table_ids:
        return []

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
        figures_to_grobid_annotations(
            paper_id,
            request.image_ids,
            request.table_ids,
            rgb_color,
        )
    )

    return all_annotations


@app.post('/papers/{paper_id}/clear-highlights', status_code=status.HTTP_204_NO_CONTENT)
def clear_highlights(
    paper_id: int,
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


@app.get('/papers/{paper_id}/chat/messages', response_model=list[dict])
def get_chat_messages(
    paper_id: int,
    session: Session = Depends(get_session),
) -> Any:
    conversation_db = (
        session.query(ConversationDB)
        .filter(ConversationDB.paper_id == paper_id)
        .first()
    )
    return conversation_db.messages if conversation_db else []


@app.delete('/papers/{paper_id}/chat')
def clear_chat(
    paper_id: int,
    session: Session = Depends(get_session),
) -> Any:
    conversation_db = (
        session.query(ConversationDB)
        .filter(ConversationDB.paper_id == paper_id)
        .first()
    )
    if conversation_db:
        session.delete(conversation_db)
    return {'status': 'cleared'}


@app.post('/papers/{paper_id}/chat/init', response_model=list[dict])
async def init_chat(
    paper_id: int,
    request: ChatMessageRequest,
    session: Session = Depends(get_session),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    conversation_db = (
        session.query(ConversationDB)
        .filter(ConversationDB.paper_id == paper_id)
        .first()
    )

    if conversation_db is None:
        any_eligible = session.query(TaskDB).filter(TaskDB.paper_id == paper_id).all()
        if not any(t.conversation_id for t in any_eligible):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='No completed task conversations available for this paper.',
            )

        def build_selection_summary(output: ChatRoutingOutput) -> str:
            parts = [f'Selected the "{output.task_type}" agent']
            if output.entity_label:
                parts.append(f'for "{output.entity_label}"')
            parts.append(f'because it {output.task_type.description.lower()}')
            return ' '.join(parts)

        routing_input = (
            f'{CHAT_ROUTING_INSTRUCTIONS}\n\nUser question: {request.message}'
        )
        routing_result = await Runner.run(make_routing_agent(paper_id), routing_input)
        routing_output = routing_result.final_output

        if routing_output.task_type == TaskType.GENERAL_PAPER_QUESTION:
            conversation_db = ConversationDB(
                paper_id=paper_id,
                conversation_id=None,
                messages=[
                    {'role': 'user', 'content': request.message},
                    {
                        'role': 'assistant',
                        'content': build_selection_summary(routing_output),
                    },
                ],
            )
        else:
            chosen_task = session.get(TaskDB, routing_output.task_id)
            if chosen_task is None or not chosen_task.conversation_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail='No agent conversation is available for the selected task type.',
                )
            conversation_db = ConversationDB(
                paper_id=paper_id,
                conversation_id=chosen_task.conversation_id,
                messages=[
                    {'role': 'user', 'content': request.message},
                    {
                        'role': 'assistant',
                        'content': build_selection_summary(routing_output),
                    },
                ],
            )

        session.add(conversation_db)

    return conversation_db.messages


def _build_qa_context(
    paper_id: int, paper_db: PaperDB, session: Session
) -> tuple[str, str, str]:
    """Build paper context and database state separately.

    Returns:
        Tuple of (paper_context, db_state_context, agent_instructions)
    """
    families = session.query(FamilyDB).filter(FamilyDB.paper_id == paper_id).all()
    family_ids = [f.id for f in families]
    patients = session.query(PatientDB).filter(PatientDB.paper_id == paper_id).all()
    pedigrees = session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).all()
    phenotypes = (
        session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == paper_id).all()
    )
    phenotype_ids = [p.id for p in phenotypes]
    hpos = (
        session.query(HpoDB).filter(HpoDB.phenotype_id.in_(phenotype_ids)).all()
        if phenotype_ids
        else []
    )
    variants = session.query(VariantDB).filter(VariantDB.paper_id == paper_id).all()
    variant_ids = [v.id for v in variants]
    harmonized = (
        session.query(HarmonizedVariantDB)
        .filter(HarmonizedVariantDB.variant_id.in_(variant_ids))
        .all()
        if variant_ids
        else []
    )
    enriched = (
        session.query(AnnotatedVariantDB)
        .filter(AnnotatedVariantDB.variant_id.in_(variant_ids))
        .all()
        if variant_ids
        else []
    )
    pvlinks = (
        session.query(PatientVariantOccurrenceDB)
        .filter(PatientVariantOccurrenceDB.paper_id == paper_id)
        .all()
    )
    seg_evidence = (
        session.query(SegregationEvidenceDB)
        .filter(SegregationEvidenceDB.family_id.in_(family_ids))
        .all()
        if family_ids
        else []
    )
    seg_computed = (
        session.query(SegregationAnalysisComputedDB)
        .filter(SegregationAnalysisComputedDB.family_id.in_(family_ids))
        .all()
        if family_ids
        else []
    )

    def _row(row: Any) -> dict:
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}

    db_state = {
        'paper': _row(paper_db),
        'families': [_row(r) for r in families],
        'patients': [_row(r) for r in patients],
        'pedigrees': [_row(r) for r in pedigrees],
        'phenotypes': [_row(r) for r in phenotypes],
        'hpo_terms': [_row(r) for r in hpos],
        'variants': [_row(r) for r in variants],
        'harmonized_variants': [_row(r) for r in harmonized],
        'annotated_variants': [_row(r) for r in enriched],
        'patient_variant_occurrences': [_row(r) for r in pvlinks],
        'segregation_evidence': [_row(r) for r in seg_evidence],
        'segregation_analysis': [_row(r) for r in seg_computed],
    }

    paper_md = relevant_sections_md(paper_id, paper_db.supplement_format)
    paper_context = f'PAPER TEXT:\n{paper_md}'
    db_state_context = f'CAA Extracted State:\n{json.dumps(db_state, default=str)}'

    return paper_context, db_state_context, GENERAL_PAPER_QA_INSTRUCTIONS


@app.post('/papers/{paper_id}/chat/generate', response_model=list[dict])
async def generate_chat_response(
    paper_id: int,
    request: ChatMessageRequest | None = None,
    session: Session = Depends(get_session),
) -> Any:
    conversation_db = (
        session.query(ConversationDB)
        .filter(ConversationDB.paper_id == paper_id)
        .first()
    )

    if conversation_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No conversation initialized for this paper.',
        )

    if request and request.message:
        conversation_db.messages = [
            *conversation_db.messages,
            {'role': 'user', 'content': request.message},
        ]
        flag_modified(conversation_db, 'messages')

    last_user_message = next(
        (
            msg['content']
            for msg in reversed(conversation_db.messages)
            if msg['role'] == 'user'
        ),
        None,
    )
    if last_user_message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No user message in conversation.',
        )

    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    if conversation_db.conversation_id is None:
        paper_context, db_state_context, agent_instructions = _build_qa_context(
            paper_id, paper_db, session
        )
        qa_input = (
            f'{paper_context}\n\n'
            f'{db_state_context}\n\n'
            f'{agent_instructions}\n\n'
            f'User question: {last_user_message}'
        )
        new_conv_id = await ensure_conversation_id(None)
        result = await Runner.run(
            general_paper_qa_agent, qa_input, conversation_id=new_conv_id
        )
        response_text = result.final_output
        conversation_db.conversation_id = new_conv_id
    else:
        client = AsyncOpenAI(api_key=env.OPENAI_API_KEY)
        resp = await client.responses.create(
            model=env.OPENAI_API_DEPLOYMENT,
            input=last_user_message,
            conversation=conversation_db.conversation_id,
        )
        response_text = resp.output_text or ''

    conversation_db.messages = [
        *conversation_db.messages,
        {'role': 'assistant', 'content': response_text},
    ]
    flag_modified(conversation_db, 'messages')
    return conversation_db.messages
