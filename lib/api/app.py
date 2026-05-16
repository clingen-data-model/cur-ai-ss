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
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from lib.agents.chat_routing_agent import ChatRoutingOutput, make_routing_agent
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
)
from lib.models import (
    ChatMessageRequest,
    ChatMessageResp,
    ChatRoutingResponse,
    ConversationDB,
    EnrichedVariantDB,
    EnrichedVariantResp,
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
    PatientVariantLinkDB,
    PatientVariantLinkResp,
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

    paper_db = PaperDB.from_content(main_content)
    paper_db.gene_id = gene.id
    paper_db.filename = uploaded_file.filename or ''
    session.add(paper_db)
    try:
        # Create initial PDF_PARSING task
        task = TaskDB(
            paper_id=paper_db.id,
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
        identifier_evidence=row.identifier_evidence,  # type: ignore[arg-type]
        proband_status=row.proband_status,  # type: ignore[arg-type]
        proband_status_evidence=row.proband_status_evidence,  # type: ignore[arg-type]
        sex=row.sex,  # type: ignore[arg-type]
        sex_evidence=row.sex_evidence,  # type: ignore[arg-type]
        age_diagnosis=row.age_diagnosis,
        age_diagnosis_unit=row.age_diagnosis_unit,
        age_diagnosis_evidence=row.age_diagnosis_evidence,  # type: ignore[arg-type]
        age_report=row.age_report,
        age_report_unit=row.age_report_unit,
        age_report_evidence=row.age_report_evidence,  # type: ignore[arg-type]
        age_death=row.age_death,
        age_death_unit=row.age_death_unit,
        age_death_evidence=row.age_death_evidence,  # type: ignore[arg-type]
        country_of_origin=row.country_of_origin,  # type: ignore[arg-type]
        country_of_origin_evidence=row.country_of_origin_evidence,  # type: ignore[arg-type]
        race_ethnicity=row.race_ethnicity,  # type: ignore[arg-type]
        race_ethnicity_evidence=row.race_ethnicity_evidence,  # type: ignore[arg-type]
        affected_status=row.affected_status,  # type: ignore[arg-type]
        affected_status_evidence=row.affected_status_evidence,  # type: ignore[arg-type]
        is_obligate_carrier=row.is_obligate_carrier,
        relationship_to_proband=row.relationship_to_proband,  # type: ignore[arg-type]
        twin_type=row.twin_type,  # type: ignore[arg-type]
        is_obligate_carrier_evidence=row.is_obligate_carrier_evidence,  # type: ignore[arg-type]
        relationship_to_proband_evidence=row.relationship_to_proband_evidence,  # type: ignore[arg-type]
        twin_type_evidence=row.twin_type_evidence,  # type: ignore[arg-type]
        updated_at=row.updated_at,
        family_id=row.family.id,
        family_identifier=row.family.identifier,
        family_assignment_evidence=row.family_assignment_evidence,  # type: ignore[arg-type]
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
    return patient_db


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
            segregation_count=ReasoningBlock(**computed.segregation_count_reasoning),  # type: ignore[arg-type]
            affected_count=ReasoningBlock(**computed.affected_count_reasoning),  # type: ignore[arg-type]
            unaffected_count=ReasoningBlock(**computed.unaffected_count_reasoning),  # type: ignore[arg-type]
            computed_lod_score=ReasoningBlock(**computed.computed_lod_score_reasoning),  # type: ignore[arg-type]
            points_assigned=ReasoningBlock(**computed.points_assigned_reasoning),  # type: ignore[arg-type]
            meets_minimum_criteria=ReasoningBlock(
                **computed.meets_minimum_criteria_reasoning
            ),  # type: ignore[arg-type]
        )

    return SegregationAnalysisResp(
        id=computed.id if computed else evidence.id,
        family_id=family.id,
        extracted_lod_score=HumanEvidenceBlock(  # type: ignore[arg-type]
            **(evidence.extracted_lod_score_evidence or {}),
        ),
        has_unexplainable_non_segregations=HumanEvidenceBlock(  # type: ignore[arg-type]
            **(evidence.has_unexplainable_non_segregations_evidence or {}),
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
            joinedload(VariantDB.harmonized_variant).joinedload(
                HarmonizedVariantDB.enriched_variant
            )
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
        EnrichedVariantResp(
            gnomad_style_coordinates=hv.enriched_variant.gnomad_style_coordinates,
            rsid=hv.enriched_variant.rsid,
            caid=hv.enriched_variant.caid,
            pathogenicity=hv.enriched_variant.pathogenicity,
            submissions=hv.enriched_variant.submissions,
            stars=hv.enriched_variant.stars,
            exon=hv.enriched_variant.exon,
            revel=hv.enriched_variant.revel,
            alphamissense_class=hv.enriched_variant.alphamissense_class,
            alphamissense_score=hv.enriched_variant.alphamissense_score,
            spliceai=hv.enriched_variant.spliceai,
            gnomad_top_level_af=hv.enriched_variant.gnomad_top_level_af,
            gnomad_popmax_af=hv.enriched_variant.gnomad_popmax_af,
            gnomad_popmax_population=hv.enriched_variant.gnomad_popmax_population,
        )
        if hv and hv.enriched_variant
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
        transcript_evidence=row.transcript_evidence,  # type: ignore[arg-type]
        protein_accession_evidence=row.protein_accession_evidence,  # type: ignore[arg-type]
        genomic_accession_evidence=row.genomic_accession_evidence,  # type: ignore[arg-type]
        lrg_accession_evidence=row.lrg_accession_evidence,  # type: ignore[arg-type]
        gene_accession_evidence=row.gene_accession_evidence,  # type: ignore[arg-type]
        genomic_coordinates_evidence=row.genomic_coordinates_evidence,  # type: ignore[arg-type]
        genome_build_evidence=row.genome_build_evidence,  # type: ignore[arg-type]
        rsid_evidence=row.rsid_evidence,  # type: ignore[arg-type]
        caid_evidence=row.caid_evidence,  # type: ignore[arg-type]
        variant_evidence=row.variant_evidence,  # type: ignore[arg-type]
        hgvs_c_evidence=row.hgvs_c_evidence,  # type: ignore[arg-type]
        hgvs_p_evidence=row.hgvs_p_evidence,  # type: ignore[arg-type]
        hgvs_g_evidence=row.hgvs_g_evidence,  # type: ignore[arg-type]
        variant_type_evidence=row.variant_type_evidence,  # type: ignore[arg-type]
        functional_evidence_evidence=row.functional_evidence_evidence,  # type: ignore[arg-type]
        main_focus=row.main_focus,
        main_focus_evidence=row.main_focus_evidence,  # type: ignore[arg-type]
        harmonized_variant=harmonized,
        enriched_variant=enriched,
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
            joinedload(VariantDB.harmonized_variant).joinedload(
                HarmonizedVariantDB.enriched_variant
            )
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
        variant_db.harmonized_variant.enriched_variant = None
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
    '/papers/{paper_id}/patient-variant-links',
    response_model=list[PatientVariantLinkResp],
)
def get_patient_variant_links(
    paper_id: int, session: Session = Depends(get_session)
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    from lib.models.patient import PatientDB

    links = (
        session.query(PatientVariantLinkDB, PatientDB.identifier)
        .join(PatientDB, PatientVariantLinkDB.patient_id == PatientDB.id)
        .filter(PatientVariantLinkDB.paper_id == paper_id)
        .order_by(PatientVariantLinkDB.patient_id, PatientVariantLinkDB.variant_id)
        .all()
    )
    return [
        _patient_variant_link_to_resp(link[0], patient_identifier=link[1])
        for link in links
    ]


def _patient_variant_link_to_resp(
    row: PatientVariantLinkDB,
    patient_identifier: str,
) -> PatientVariantLinkResp:
    """Convert PatientVariantLinkDB to PatientVariantLinkResp."""
    from lib.models import Inheritance, TestingMethod, Zygosity

    return PatientVariantLinkResp(
        paper_id=row.paper_id,
        patient_id=row.patient_id,
        patient_identifier=patient_identifier,
        variant_id=row.variant_id,
        zygosity=Zygosity(row.zygosity),
        zygosity_evidence=EvidenceBlock.model_validate(row.zygosity_evidence),
        inheritance=Inheritance(row.inheritance),
        inheritance_evidence=EvidenceBlock.model_validate(row.inheritance_evidence),
        testing_methods=[TestingMethod(m) for m in row.testing_methods],
        testing_methods_evidence=[
            EvidenceBlock.model_validate(m) for m in row.testing_methods_evidence
        ],
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
    limit: int = Query(10),
    session: Session = Depends(get_session),
) -> Any:
    query = session.query(GeneDB).order_by(GeneDB.symbol).limit(limit)
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
        session.commit()
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

        routing_result = await Runner.run(make_routing_agent(paper_id), request.message)
        routing_output = routing_result.final_output
        chosen_task_id = routing_output.task_id
        chosen_task = session.get(TaskDB, chosen_task_id)
        if chosen_task is None or not chosen_task.conversation_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f'Routing agent returned invalid task_id {chosen_task_id}.',
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
        session.refresh(conversation_db)
    else:
        conversation_db.messages = [
            *conversation_db.messages,
            {'role': 'user', 'content': request.message},
        ]

    return conversation_db.messages


@app.post('/papers/{paper_id}/chat/generate', response_model=list[dict])
async def generate_chat_response(
    paper_id: int,
    session: Session = Depends(get_session),
) -> Any:
    SYSTEM_INSTRUCTIONS = (
        'You are an expert clinical genomics assistant helping users understand extracted data from research papers. '
        'The system has extracted patients, variants, phenotypes, and their relationships from a paper. '
        'You answer questions about this extracted data, help interpret findings, and clarify relationships between entities. '
        'Keep responses short and precise.'
    )

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

    last_user_message = next(
        (msg['content'] for msg in reversed(conversation_db.messages) if msg['role'] == 'user'),
        None,
    )
    if last_user_message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No user message in conversation.',
        )

    client = AsyncOpenAI(api_key=env.OPENAI_API_KEY)
    resp = await client.responses.create(
        model=env.OPENAI_API_DEPLOYMENT,
        input=last_user_message,
        conversation=conversation_db.conversation_id,
        instructions=SYSTEM_INSTRUCTIONS,
    )
    response_text = resp.output_text or ''
    conversation_db.messages = [
        *conversation_db.messages,
        {'role': 'assistant', 'content': response_text},
    ]
    return conversation_db.messages
