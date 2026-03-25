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
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
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
    EnrichedVariantDB,
    EnrichedVariantResp,
    ExtractedPhenotype,
    ExtractedPhenotypeDB,
    ExtractedPhenotypeResp,
    ExtractedPhenotypeUpdateRequest,
    ExtractedVariantDB,
    ExtractedVariantResp,
    GeneDB,
    GeneResp,
    HarmonizedVariantDB,
    HarmonizedVariantResp,
    HighlightRequest,
    HpoDB,
    HPOTerm,
    PaperDB,
    PaperResp,
    PaperUpdateRequest,
    PatientDB,
    PatientResp,
    PatientUpdateRequest,
    PatientVariantLinkDB,
    PatientVariantLinkResp,
    PedigreeDB,
    PedigreeResp,
    PipelineStatus,
)
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock

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


@app.get('/papers/{paper_id}/pedigree', response_model=PedigreeResp | None)
def get_pedigree(paper_id: str, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    pedigree = (
        session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).one_or_none()
    )
    return pedigree


@app.get('/papers/{paper_id}/variants', response_model=list[ExtractedVariantResp])
def get_variants(paper_id: str, session: Session = Depends(get_session)) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    variants = (
        session.query(ExtractedVariantDB)
        .options(
            joinedload(ExtractedVariantDB.harmonized_variant).joinedload(
                HarmonizedVariantDB.enriched_variant
            )
        )
        .filter(ExtractedVariantDB.paper_id == paper_id)
        .order_by(ExtractedVariantDB.variant_idx)
        .all()
    )
    return [_variant_to_resp(v) for v in variants]


def _variant_to_resp(row: ExtractedVariantDB) -> ExtractedVariantResp:
    """Convert ExtractedVariantDB to ExtractedVariantResp, including harmonized and enriched data."""
    hv = row.harmonized_variant
    harmonized = (
        HarmonizedVariantResp(
            gnomad_style_coordinates=hv.gnomad_style_coordinates,
            rsid=hv.rsid,
            caid=hv.caid,
            hgvs_c=hv.hgvs_c,
            hgvs_p=hv.hgvs_p,
            hgvs_g=hv.hgvs_g,
            reasoning=hv.reasoning,
        )
        if hv
        else None
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
    return ExtractedVariantResp(
        paper_id=row.paper_id,
        variant_idx=row.variant_idx,
        gene=row.gene,
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
        variant_type_evidence=EvidenceBlock.model_validate(row.variant_type_evidence),
        functional_evidence_evidence=EvidenceBlock.model_validate(
            row.functional_evidence_evidence
        ),
        harmonized_variant=harmonized,
        enriched_variant=enriched,
    )


def _phenotype_to_resp(row: ExtractedPhenotypeDB) -> ExtractedPhenotypeResp:
    hpo = (
        ReasoningBlock[HPOTerm | None].model_validate(row.hpo.hpo_evidence)
        if row.hpo
        else None
    )
    return ExtractedPhenotypeResp(
        paper_id=row.paper_id,
        patient_idx=row.patient_idx,
        phenotype_idx=row.phenotype_idx,
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
    paper_id: str, session: Session = Depends(get_session)
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    links = (
        session.query(PatientVariantLinkDB)
        .filter(PatientVariantLinkDB.paper_id == paper_id)
        .order_by(PatientVariantLinkDB.patient_idx, PatientVariantLinkDB.variant_idx)
        .all()
    )
    return [_patient_variant_link_to_resp(link) for link in links]


def _patient_variant_link_to_resp(
    row: PatientVariantLinkDB,
) -> PatientVariantLinkResp:
    """Convert PatientVariantLinkDB to PatientVariantLinkResp."""
    from lib.models import Inheritance, TestingMethod, Zygosity

    return PatientVariantLinkResp(
        paper_id=row.paper_id,
        patient_idx=row.patient_idx,
        variant_idx=row.variant_idx,
        zygosity=Zygosity(row.zygosity),
        zygosity_evidence=EvidenceBlock.model_validate(row.zygosity_evidence),
        inheritance=Inheritance(row.inheritance),
        inheritance_evidence=EvidenceBlock.model_validate(row.inheritance_evidence),
        testing_methods=[
            EvidenceBlock.model_validate(m) for m in row.testing_methods
        ],
        updated_at=row.updated_at,
    )


@app.get(
    '/papers/{paper_id}/patients/{patient_idx}/phenotypes',
    response_model=list[ExtractedPhenotypeResp],
)
def get_phenotypes(
    paper_id: str, patient_idx: int, session: Session = Depends(get_session)
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patient_db = (
        session.query(PatientDB)
        .filter(PatientDB.paper_id == paper_id, PatientDB.patient_idx == patient_idx)
        .one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    phenotypes = (
        session.query(ExtractedPhenotypeDB)
        .options(joinedload(ExtractedPhenotypeDB.hpo))
        .filter(
            ExtractedPhenotypeDB.paper_id == paper_id,
            ExtractedPhenotypeDB.patient_idx == patient_idx,
        )
        .order_by(ExtractedPhenotypeDB.phenotype_idx)
        .all()
    )
    return [_phenotype_to_resp(p) for p in phenotypes]


@app.post(
    '/papers/{paper_id}/patients/{patient_idx}/phenotypes',
    response_model=ExtractedPhenotypeResp,
)
def create_phenotype(
    paper_id: str,
    patient_idx: int,
    phenotype_data: ExtractedPhenotype,
    session: Session = Depends(get_session),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patient_db = (
        session.query(PatientDB)
        .filter(PatientDB.paper_id == paper_id, PatientDB.patient_idx == patient_idx)
        .one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )

    # Get next phenotype_idx for this patient
    max_phenotype_idx = (
        session.query(func.max(ExtractedPhenotypeDB.phenotype_idx))
        .filter(
            ExtractedPhenotypeDB.paper_id == paper_id,
            ExtractedPhenotypeDB.patient_idx == patient_idx,
        )
        .scalar()
    ) or 0
    next_phenotype_idx = max_phenotype_idx + 1

    phenotype_db = ExtractedPhenotypeDB(
        paper_id=paper_id,
        patient_idx=patient_idx,
        phenotype_idx=next_phenotype_idx,
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
    session.commit()
    session.refresh(phenotype_db)
    return phenotype_db


@app.patch(
    '/papers/{paper_id}/patients/{patient_idx}/phenotypes/{phenotype_idx}',
    response_model=ExtractedPhenotypeResp,
)
def update_phenotype(
    paper_id: str,
    patient_idx: int,
    phenotype_idx: int,
    patch_request: ExtractedPhenotypeUpdateRequest,
    session: Session = Depends(get_session),
) -> Any:
    phenotype_db = (
        session.query(ExtractedPhenotypeDB)
        .filter(
            ExtractedPhenotypeDB.paper_id == paper_id,
            ExtractedPhenotypeDB.patient_idx == patient_idx,
            ExtractedPhenotypeDB.phenotype_idx == phenotype_idx,
        )
        .one_or_none()
    )
    if not phenotype_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Phenotype not found'
        )
    patch_request.apply_to(phenotype_db)
    session.commit()
    session.refresh(phenotype_db)
    return phenotype_db


@app.patch('/papers/{paper_id}/patients/{patient_idx}', response_model=PatientResp)
def update_patient(
    paper_id: str,
    patient_idx: int,
    patch_request: PatientUpdateRequest,
    session: Session = Depends(get_session),
) -> Any:
    patient_db = (
        session.query(PatientDB)
        .filter(PatientDB.patient_idx == patient_idx, PatientDB.paper_id == paper_id)
        .one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    patch_request.apply_to(patient_db)
    return patient_db


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
