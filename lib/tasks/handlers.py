import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from agents import Agent, RunConfig, Runner
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from lib.agents.hpo_linking_agent import (
    HPO_LINKING_AGENT_INSTRUCTIONS,
)
from lib.agents.hpo_linking_agent import (
    agent as hpo_linking_agent,
)
from lib.agents.paper_extraction_agent import (
    PAPER_EXTRACTION_AGENT_INSTRUCTIONS,
)
from lib.agents.paper_extraction_agent import (
    agent as paper_extraction_agent,
)
from lib.agents.paper_section_classifier_agent import (
    PAPER_SECTION_CLASSIFIER_AGENT_INSTRUCTIONS,
)
from lib.agents.paper_section_classifier_agent import (
    agent as paper_section_classifier_agent,
)
from lib.agents.patient_extraction_agent import (
    PATIENT_EXTRACTION_AGENT_INSTRUCTIONS,
)
from lib.agents.patient_extraction_agent import (
    agent as patient_extraction_agent,
)
from lib.agents.patient_phenotype_linking_agent import (
    PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS,
)
from lib.agents.patient_phenotype_linking_agent import (
    agent as patient_phenotype_linking_agent,
)
from lib.agents.patient_variant_linking_agent import (
    PATIENT_VARIANT_LINKING_AGENT_INSTRUCTIONS,
)
from lib.agents.patient_variant_linking_agent import (
    agent as patient_variant_linking_agent,
)
from lib.agents.pedigree_describer_agent import (
    PEDIGREE_DESCRIBER_AGENT_INSTRUCTIONS,
)
from lib.agents.pedigree_describer_agent import (
    agent as pedigree_describer_agent,
)
from lib.agents.segregation_analysis_computed_agent import (
    SEGREGATION_ANALYSIS_COMPUTED_AGENT_INSTRUCTIONS,
)
from lib.agents.segregation_analysis_computed_agent import (
    agent as segregation_analysis_computed_agent,
)
from lib.agents.segregation_evidence_extractor import (
    SEGREGATION_EVIDENCE_AGENT_INSTRUCTIONS,
)
from lib.agents.segregation_evidence_extractor import (
    agent as segregation_evidence_extractor,
)
from lib.agents.variant_annotation_agent import enrich_variants_batch
from lib.agents.variant_extraction_agent import (
    VARIANT_EXTRACTION_AGENT_INSTRUCTIONS,
)
from lib.agents.variant_extraction_agent import (
    agent as variant_extraction_agent,
)
from lib.agents.variant_harmonization_agent import (
    VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS,
)
from lib.agents.variant_harmonization_agent import (
    agent as variant_harmonization_agent,
)
from lib.api.db import session_scope
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.gcs import upload_and_sign_image
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import (
    fulltext_md,
    pdf_image_caption_path,
    pdf_image_path,
    relevant_sections_md,
)
from lib.models import (
    EnrichedVariantDB,
    FamilyDB,
    HarmonizedVariantDB,
    HpoDB,
    PaperDB,
    PatientDB,
    PatientVariantLinkDB,
    PedigreeDB,
    PhenotypeDB,
    SegregationAnalysisComputedDB,
    SegregationEvidenceDB,
    TaskDB,
    VariantDB,
    Zygosity,
)
from lib.models.converters import (
    family_to_db,
    harmonized_variant_to_db,
    hpo_to_db,
    patient_to_db,
    patient_variant_link_to_db,
    pedigree_to_db,
    phenotype_to_db,
    segregation_analysis_computed_to_db,
    segregation_evidence_to_db,
    variant_to_db,
)
from lib.models.evidence_block import ReasoningBlock
from lib.models.paper import FileFormat
from lib.models.phenotype import HPOTerm
from lib.models.variant import HarmonizedVariant, Variant
from lib.reference_data.hpo import build_term_lookup, find_matching_hpo_terms
from lib.tasks.models import TaskType

setup_logging()
logger = logging.getLogger(__name__)


def log_cache_metrics(task_type: str, result: Any) -> None:
    """Log prompt cache metrics from agent response."""
    if not hasattr(result, 'raw_responses') or not result.raw_responses:
        return

    total_input = 0
    total_cache_read = 0

    for resp in result.raw_responses:
        if not hasattr(resp, 'usage'):
            continue

        usage = resp.usage
        input_tokens = usage.input_tokens or 0
        cache_read = (
            usage.input_tokens_details.cached_tokens
            if usage.input_tokens_details and usage.input_tokens_details.cached_tokens
            else 0
        )

        total_input += input_tokens
        total_cache_read += cache_read

    if total_input > 0:
        cache_pct = (total_cache_read / total_input * 100) if total_input > 0 else 0
        logger.info(
            f'[CACHE] {task_type}: '
            f'input={total_input} cached={total_cache_read} '
            f'({cache_pct:.1f}%)'
        )


async def ensure_conversation_id(conversation_id: str | None) -> str:
    """Create a new conversation if needed, otherwise return the provided ID."""
    if conversation_id:
        return conversation_id

    client = AsyncOpenAI(api_key=env.OPENAI_API_KEY)
    conversation = await client.conversations.create()
    return conversation.id


def build_followup_prompt(additional_context: str) -> str:
    """Build a follow-up prompt for continuing an existing agent conversation.

    Args:
        additional_context: Context/feedback to provide to the agent

    Returns:
        Formatted follow-up prompt
    """
    return f'Please review your previous analysis in light of the following additional context:\n\n{additional_context}'


def format_paper_context(paper_markdown: str, gene_symbol: str | None = None) -> str:
    """Format paper and gene context for inclusion in message input.

    Args:
        paper_markdown: The full paper content
        gene_symbol: Optional gene symbol to include

    Returns:
        Formatted paper context string
    """
    sections = [
        'PAPER AND GENE CONTEXT',
        f'Paper (fulltext md):\n{paper_markdown}',
    ]
    if gene_symbol:
        sections.append(f'Gene: {gene_symbol}')
    return '\n\n'.join(sections)


async def handle_pdf_parsing(task_id: int) -> None:
    """Parse PDF to markdown and extract images/tables."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return
        paper_id = task.paper_id
        paper = session.get(PaperDB, paper_id)
        supplement_format = paper.supplement_format if paper else None

    await parse_content(paper_id, force=True)
    if supplement_format:
        await parse_content(paper_id, force=True, supplement_format=supplement_format)


async def handle_paper_section_classifier(task_id: int) -> None:
    """Classify paper sections as relevant or irrelevant for downstream extraction."""
    paper_id: int
    gene_symbol: str
    stored_conv_id: str | None
    additional_context: str | None
    supplement_format: FileFormat | None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        paper = session.get(PaperDB, task.paper_id) if task else None
        if not task or not paper:
            return
        paper_id = task.paper_id
        gene_symbol = paper.gene.symbol
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context
        supplement_format = paper.supplement_format

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
        agent = paper_section_classifier_agent
    else:
        # Initial query: build full message with paper + instructions
        paper_markdown = fulltext_md(paper_id, supplement_format)
        paper_context = format_paper_context(paper_markdown, gene_symbol)
        message = f'{paper_context}\n\n{PAPER_SECTION_CLASSIFIER_AGENT_INSTRUCTIONS}'
        agent = paper_section_classifier_agent

    result = await Runner.run(agent, message, conversation_id=stored_conv_id)
    log_cache_metrics('PAPER_SECTION_CLASSIFIER', result)

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        paper = session.get(PaperDB, paper_id)
        if task:
            task.conversation_id = stored_conv_id
            # If paper is not relevant, skip enqueuing successors
            if not result.final_output.is_paper_relevant:
                task.skip_successors = True
        if paper:
            paper.is_paper_relevant = result.final_output.is_paper_relevant
            paper.section_classifications = result.final_output.model_dump()


async def handle_paper_metadata(task_id: int) -> None:
    """Extract paper metadata (title, authors, abstract, etc)."""
    paper_id: int
    gene_symbol: str
    stored_conv_id: str | None
    additional_context: str | None
    supplement_format: FileFormat | None
    section_classifications: dict | None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        paper_id = task.paper_id
        gene_symbol = paper.gene.symbol
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context
        supplement_format = paper.supplement_format
        section_classifications = paper.section_classifications

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
        agent = paper_extraction_agent
    else:
        # Initial query: build full message with paper + instructions
        paper_markdown = relevant_sections_md(
            paper_id, supplement_format, section_classifications
        )
        paper_context = format_paper_context(paper_markdown, gene_symbol)
        message = f'{paper_context}\n\n{PAPER_EXTRACTION_AGENT_INSTRUCTIONS}'
        agent = paper_extraction_agent

    result = await Runner.run(
        agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('PAPER_METADATA', result)

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if task:
            task.conversation_id = stored_conv_id
        paper = session.get(PaperDB, paper_id)
        if paper:
            result.final_output.apply_to(paper)


async def handle_variant_extraction(task_id: int) -> None:
    """Extract genetic variants from paper."""
    paper_id: int
    gene_symbol: str
    stored_conv_id: str | None
    additional_context: str | None
    supplement_format: FileFormat | None
    section_classifications: dict | None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        paper_id = task.paper_id
        gene_symbol = paper.gene.symbol
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context
        supplement_format = paper.supplement_format
        section_classifications = paper.section_classifications

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
        agent = variant_extraction_agent
    else:
        # Initial query: build full message with paper + instructions
        paper_markdown = relevant_sections_md(
            paper_id, supplement_format, section_classifications
        )
        paper_context = format_paper_context(paper_markdown, gene_symbol)
        message = f'{paper_context}\n\n{VARIANT_EXTRACTION_AGENT_INSTRUCTIONS}'
        agent = variant_extraction_agent

    result = await Runner.run(
        agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('VARIANT_EXTRACTION', result)

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return
        agent_run_id = task.agent_run_id
        task.conversation_id = stored_conv_id

        # Idempotent: delete-then-insert (only from current run)
        session.query(VariantDB).filter(
            VariantDB.paper_id == paper_id,
            VariantDB.agent_run_id == agent_run_id,
        ).delete()
        for variant in result.final_output.variants:
            session.add(variant_to_db(paper_id, variant, agent_run_id))


async def handle_pedigree_description(task_id: int) -> None:
    """Describe pedigree images from paper."""
    paper_id: int
    stored_conv_id: str | None
    additional_context: str | None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return
        paper_id = task.paper_id
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

    combined_text = ''

    # Process regular images
    image_id = 0
    while True:
        pdf_image = pdf_image_path(paper_id, image_id)
        if not pdf_image.exists():
            break
        caption_path = pdf_image_caption_path(paper_id, image_id)
        caption_text = (
            caption_path.read_text() if caption_path.exists() else 'No caption'
        )
        # Upload image to GCS and get signed URL
        logger.info(f'Processing image {image_id} from {pdf_image}')
        image_url = upload_and_sign_image(pdf_image)
        logger.info(
            f'Image {image_id} URL type: {type(image_url)}, starts with: {image_url[:50] if image_url else "None"}'
        )
        combined_text += f'[Processing Pipeline Figure {image_id}]\n'
        combined_text += f'URL: {image_url}\n'
        combined_text += f'Caption: {caption_text}\n\n'
        image_id += 1

    # Process supplement images
    image_id = 0
    while True:
        pdf_image = pdf_image_path(paper_id, image_id, supplement=True)
        if not pdf_image.exists():
            break
        caption_path = pdf_image_caption_path(paper_id, image_id, supplement=True)
        caption_text = (
            caption_path.read_text() if caption_path.exists() else 'No caption'
        )
        # Upload image to GCS and get signed URL
        logger.info(f'Processing supplement image {image_id} from {pdf_image}')
        image_url = upload_and_sign_image(pdf_image)
        logger.info(
            f'Supplement image {image_id} URL type: {type(image_url)}, starts with: {image_url[:50] if image_url else "None"}'
        )
        combined_text += f'[Processing Supplement Figure {image_id}]\n'
        combined_text += f'URL: {image_url}\n'
        combined_text += f'Caption: {caption_text}\n\n'
        image_id += 1

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
    else:
        # Initial query: build full message with pedigree images + instructions
        message = f'{combined_text}\n\n{PEDIGREE_DESCRIBER_AGENT_INSTRUCTIONS}'

    result = await Runner.run(
        pedigree_describer_agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('PEDIGREE_DESCRIPTION', result)

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if task:
            task.conversation_id = stored_conv_id
        # Idempotent: delete-then-insert
        session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).delete()
        if result.final_output and result.final_output.found:
            session.add(pedigree_to_db(paper_id, result.final_output))


async def handle_patient_extraction(task_id: int) -> None:
    """Extract patient information from paper."""
    paper_id: int
    pedigree_descriptions_output: dict | None
    stored_conv_id: str | None
    additional_context: str | None
    supplement_format: FileFormat | None = None
    section_classifications: dict | None = None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper_id = task.paper_id
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

        # Load paper and pedigree from DB
        paper = session.get(PaperDB, paper_id)
        supplement_format = paper.supplement_format if paper else None
        section_classifications = paper.section_classifications if paper else None

        pedigree_row = (
            session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation, just pass new instructions
        message = build_followup_prompt(additional_context)
        agent = patient_extraction_agent
    else:
        # Initial query: build full message with paper + task input + instructions
        paper_markdown = relevant_sections_md(
            paper_id, supplement_format, section_classifications
        )
        paper_context = format_paper_context(paper_markdown)
        message = (
            f'{paper_context}\n\n'
            f'Pedigree Description:\n{pedigree_descriptions_output}\n\n'
            f'{PATIENT_EXTRACTION_AGENT_INSTRUCTIONS}'
        )
        agent = patient_extraction_agent

    result = await Runner.run(
        agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('PATIENT_EXTRACTION', result)

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return
        agent_run_id = task.agent_run_id
        task.conversation_id = stored_conv_id

        # Idempotent: delete patients (CASCADE deletes families) only from current run, then re-insert both
        session.query(PatientDB).filter(
            PatientDB.paper_id == paper_id,
            PatientDB.agent_run_id == agent_run_id,
        ).delete()
        session.flush()

        # Insert families first so we have family IDs for patient assignment
        family_entries_by_id: dict[str, int] = {}
        for entry in result.final_output.families:
            db_family = family_to_db(paper_id, entry.family)
            session.add(db_family)
            session.flush()
            family_entries_by_id[entry.family.identifier.value] = db_family.id

        # Insert patients with family assignments
        for patient_info in result.final_output.patients:
            db_patient = patient_to_db(paper_id, patient_info, agent_run_id)
            # Use family_identifier from patient to find correct family
            family_id_value = patient_info.family_identifier.value
            if family_id_value in family_entries_by_id:
                db_patient.family_id = family_entries_by_id[family_id_value]
                db_patient.family_assignment_evidence = (
                    patient_info.family_identifier.model_dump()
                )
            session.add(db_patient)


async def handle_segregation_evidence_extraction(task_id: int) -> None:
    """Extract segregation evidence from paper for a specific family."""
    paper_id: int = 0
    family_id: int | None = None
    supplement_format: FileFormat | None = None
    stored_conv_id: str | None = None
    additional_context: str | None = None
    family_info: dict | None = None
    section_classifications: dict | None = None

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        family_id = task.family_id
        if family_id is None:
            raise ValueError(
                f'Task {task_id}: SEGREGATION_EVIDENCE_EXTRACTION requires family_id'
            )

        paper_id = task.paper_id
        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        supplement_format = paper.supplement_format
        section_classifications = paper.section_classifications
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

        family = session.get(FamilyDB, family_id)
        if not family:
            return

        # Load patients in family
        patients = (
            session.query(PatientDB).filter(PatientDB.family_id == family_id).all()
        )

        # Load variant links for this family
        patient_ids = [p.id for p in patients]
        variant_links = (
            session.query(PatientVariantLinkDB)
            .filter(PatientVariantLinkDB.patient_id.in_(patient_ids))
            .all()
            if patient_ids
            else []
        )

        # Build family structure info
        family_info = {
            'family_identifier': family.identifier,
            'patients': [
                {
                    'id': p.id,
                    'identifier': p.identifier,
                    'affected_status': p.affected_status,
                    'proband_status': p.proband_status,
                }
                for p in patients
            ],
            'patient_variant_links': [
                {
                    'patient_id': vl.patient_id,
                    'variant_id': vl.variant_id,
                    'zygosity': vl.zygosity,
                }
                for vl in variant_links
            ],
        }

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
        agent = segregation_evidence_extractor
    else:
        # Initial query: build full message with paper + family data + instructions
        paper_markdown = relevant_sections_md(
            paper_id, supplement_format, section_classifications
        )
        paper_context = format_paper_context(paper_markdown)
        message = (
            f'{paper_context}\n\n'
            f'Family Structure: {json.dumps(family_info, indent=2, default=str)}\n\n'
            f'{SEGREGATION_EVIDENCE_AGENT_INSTRUCTIONS}'
        )
        agent = segregation_evidence_extractor

    result = await Runner.run(
        agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('SEGREGATION_EVIDENCE_EXTRACTION', result)

    # Store results in new session
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_id = stored_conv_id

        session.query(SegregationEvidenceDB).filter(
            SegregationEvidenceDB.family_id == family_id
        ).delete()
        session.flush()

        # Convert and insert
        db_evidence = segregation_evidence_to_db(family_id, result.final_output)
        session.add(db_evidence)


async def handle_segregation_analysis_computed(task_id: int) -> None:
    """Compute segregation analysis metrics for a specific family using ClinGen methodology."""
    family_id: int | None = None
    stored_conv_id: str | None = None
    additional_context: str | None = None
    family_info: dict | None = None
    paper_id: int | None = None
    supplement_format: FileFormat | None = None
    section_classifications: dict | None = None

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        family_id = task.family_id
        if family_id is None:
            raise ValueError(
                f'Task {task_id}: SEGREGATION_ANALYSIS_COMPUTED requires family_id'
            )

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        paper_id = task.paper_id
        supplement_format = paper.supplement_format
        section_classifications = paper.section_classifications
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

        family = session.get(FamilyDB, family_id)
        if not family:
            return

        # Load patients in family
        patients = (
            session.query(PatientDB).filter(PatientDB.family_id == family_id).all()
        )

        # Load variant links for this family
        patient_ids = [p.id for p in patients]
        variant_links = (
            session.query(PatientVariantLinkDB)
            .filter(PatientVariantLinkDB.patient_id.in_(patient_ids))
            .all()
            if patient_ids
            else []
        )

        # Load segregation evidence for this family
        seg_evidence = (
            session.query(SegregationEvidenceDB)
            .filter(SegregationEvidenceDB.family_id == family_id)
            .first()
        )

        # Build input for agent
        family_info = {
            'family_identifier': family.identifier,
            'patients': [
                {
                    'id': p.id,
                    'identifier': p.identifier,
                    'affected_status': p.affected_status,
                    'proband_status': p.proband_status,
                    'sex': p.sex,
                }
                for p in patients
            ],
            'patient_variant_links': [
                {
                    'patient_id': vl.patient_id,
                    'variant_id': vl.variant_id,
                    'zygosity': vl.zygosity,
                    'inheritance': vl.inheritance,
                    'testing_methods': vl.testing_methods,
                }
                for vl in variant_links
            ],
            'segregation_evidence': {
                'extracted_lod_score': seg_evidence.extracted_lod_score
                if seg_evidence
                else None,
                'has_unexplainable_non_segregations': seg_evidence.has_unexplainable_non_segregations
                if seg_evidence
                else None,
            }
            if seg_evidence
            else None,
        }

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
    else:
        # Initial query: build full message with paper + family data + instructions
        paper_markdown = relevant_sections_md(
            paper_id, supplement_format, section_classifications
        )
        paper_context = format_paper_context(paper_markdown)
        message = (
            f'{paper_context}\n\n'
            f'Family Structure and Data: {json.dumps(family_info, indent=2, default=str)}\n\n'
            f'{SEGREGATION_ANALYSIS_COMPUTED_AGENT_INSTRUCTIONS}'
        )

    result = await Runner.run(
        segregation_analysis_computed_agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('SEGREGATION_ANALYSIS_COMPUTED', result)

    # Store results in new session
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_id = stored_conv_id

        session.query(SegregationAnalysisComputedDB).filter(
            SegregationAnalysisComputedDB.family_id == family_id
        ).delete()
        session.flush()

        # Convert and insert
        db_computed = segregation_analysis_computed_to_db(
            family_id, result.final_output
        )
        session.add(db_computed)


async def handle_variant_harmonization(task_id: int) -> None:
    """Harmonize a variant to standard genomic coordinates."""
    variant_id: int | None = None
    stored_conv_id: str | None = None
    additional_context: str | None = None
    variant_input: dict | None = None

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        variant_id = task.variant_id
        if variant_id is None:
            raise ValueError(
                f'Task {task_id}: VARIANT_HARMONIZATION requires variant_id'
            )

        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        variant_row = session.get(VariantDB, variant_id)
        if not variant_row:
            return

        # Extract variant payload
        variant_input = {
            'gene_symbol': paper.gene.symbol,
            **{f: getattr(variant_row, f) for f in Variant.model_fields},
        }

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
    else:
        # Initial query: build full message with variant data + instructions
        message = (
            f'Variant JSON:\n{json.dumps(variant_input, indent=2)}\n\n'
            f'{VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS}'
        )

    result = await Runner.run(
        variant_harmonization_agent,
        message,
        max_turns=15,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('VARIANT_HARMONIZATION', result)

    # Update DB with results
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_id = stored_conv_id

        # Idempotent: delete-then-insert
        session.query(HarmonizedVariantDB).filter(
            HarmonizedVariantDB.variant_id == variant_id
        ).delete()

        session.add(harmonized_variant_to_db(variant_id, result.final_output))


async def handle_variant_annotation(task_id: int) -> None:
    """Enrich harmonized variants with annotations."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        if task.variant_id is None:
            raise ValueError(f'Task {task_id}: VARIANT_ANNOTATION requires variant_id')

        query = (
            session.query(HarmonizedVariantDB)
            .join(VariantDB, HarmonizedVariantDB.variant_id == VariantDB.id)
            .filter(VariantDB.paper_id == task.paper_id)
            .filter(HarmonizedVariantDB.variant_id == task.variant_id)
        )
        rows = query.order_by(VariantDB.id).all()

        # Skip enrichment if harmonization did not succeed
        # A successful harmonization must have at least one meaningful identifier
        rows = [
            r
            for r in rows
            if any(
                [
                    r.gnomad_style_coordinates,
                    r.rsid,
                    r.caid,
                    r.hgvs_g,
                    r.hgvs_c,
                ]
            )
        ]

        if not rows:
            logger.info(
                f'Task {task_id}: Skipping enrichment - variant failed to harmonize'
            )
            return

        harmonized_variants = [
            HarmonizedVariant(
                gnomad_style_coordinates=r.gnomad_style_coordinates,
                rsid=r.rsid,
                caid=r.caid,
                hgvs_c=r.hgvs_c,
                hgvs_p=r.hgvs_p,
                hgvs_g=r.hgvs_g,
            )
            for r in rows
        ]
        variant_ids = [r.variant_id for r in rows]

    # Offload blocking enrichment to thread (outside session context)
    enriched_variants = await asyncio.to_thread(
        enrich_variants_batch,
        harmonized_variants,
    )

    # Store results in new session
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        # Idempotent: delete-then-insert (for this specific variant)
        session.query(EnrichedVariantDB).filter(
            EnrichedVariantDB.variant_id == task.variant_id
        ).delete()

        for var_id, ev in zip(variant_ids, enriched_variants):
            session.add(
                EnrichedVariantDB(
                    variant_id=var_id,
                    gnomad_style_coordinates=ev.gnomad_style_coordinates,
                    rsid=ev.rsid,
                    caid=ev.caid,
                    pathogenicity=ev.pathogenicity,
                    submissions=ev.submissions,
                    stars=ev.stars,
                    exon=ev.exon,
                    revel=ev.revel,
                    alphamissense_class=ev.alphamissense_class,
                    alphamissense_score=ev.alphamissense_score,
                    spliceai=ev.spliceai.model_dump() if ev.spliceai else None,
                    gnomad_top_level_af=ev.gnomad_top_level_af,
                    gnomad_popmax_af=ev.gnomad_popmax_af,
                    gnomad_popmax_population=ev.gnomad_popmax_population,
                )
            )


async def handle_patient_variant_linking(task_id: int) -> None:
    """Link patients to variants with inheritance info."""
    paper_id: int
    structured_variants: list
    structured_patients: list
    pedigree_descriptions_output: dict | None
    stored_conv_id: str | None
    additional_context: str | None
    supplement_format: FileFormat | None = None
    section_classifications: dict | None = None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper_id = task.paper_id
        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

        paper = session.get(PaperDB, paper_id)
        supplement_format = paper.supplement_format if paper else None
        section_classifications = paper.section_classifications if paper else None

        variant_rows = (
            session.query(VariantDB)
            .filter(VariantDB.paper_id == paper_id)
            .order_by(VariantDB.id)
            .all()
        )
        structured_variants = [
            {
                'variant_id': v.id,
                'variant_quote': v.variant_evidence['value'],
            }
            for v in variant_rows
        ]

        patient_rows = (
            session.query(PatientDB)
            .filter(PatientDB.paper_id == paper_id)
            .order_by(PatientDB.id)
            .all()
        )
        structured_patients = [
            {
                'patient_id': p.id,
                'identifier': p.identifier,
                'identifier_quote': p.identifier_evidence['quote'],
            }
            for p in patient_rows
        ]

        pedigree_row = (
            session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
        agent = patient_variant_linking_agent
    else:
        # Initial query: build full message with paper + variant/patient data + instructions
        paper_markdown = relevant_sections_md(
            paper_id, supplement_format, section_classifications
        )
        paper_context = format_paper_context(paper_markdown)
        message = (
            f'{paper_context}\n\n'
            f'Variants JSON:\n{structured_variants}\n\n'
            f'Patients JSON:\n{structured_patients}\n\n'
            f'Pedigree Description:\n{pedigree_descriptions_output}\n\n'
            f'{PATIENT_VARIANT_LINKING_AGENT_INSTRUCTIONS}'
        )
        agent = patient_variant_linking_agent

    result = await Runner.run(
        agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('PATIENT_VARIANT_LINKING', result)

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if task:
            task.conversation_id = stored_conv_id
        # Idempotent: delete-then-insert
        session.query(PatientVariantLinkDB).filter(
            PatientVariantLinkDB.paper_id == paper_id
        ).delete()
        for link in result.final_output.links:
            session.add(patient_variant_link_to_db(paper_id, link))
        session.flush()

        # Diplotype grouping: pair exactly-2 heterozygous variants per patient
        links = (
            session.query(PatientVariantLinkDB)
            .filter(PatientVariantLinkDB.paper_id == paper_id)
            .order_by(PatientVariantLinkDB.patient_id, PatientVariantLinkDB.id)
            .all()
        )

        # Clear any existing pairing (idempotent re-run support)
        for link in links:
            link.paired_variant_link_id = None
        session.flush()

        # Group by patient and find exactly-2 heterozygous pairs
        from collections import defaultdict

        links_by_patient: dict[int, list[PatientVariantLinkDB]] = defaultdict(list)
        for link in links:
            links_by_patient[link.patient_id].append(link)

        for patient_id, patient_links in links_by_patient.items():
            het_links = [
                lnk
                for lnk in patient_links
                if lnk.zygosity == Zygosity.heterozygous.value
            ]
            if len(het_links) == 2:
                link_a, link_b = het_links[0], het_links[1]
                link_a.paired_variant_link_id = link_b.id
                link_b.paired_variant_link_id = link_a.id


async def handle_phenotype_extraction(task_id: int) -> None:
    """Extract phenotypes for a specific patient in paper."""
    paper_id: int
    patient_id: int | None = None
    supplement_format: FileFormat | None = None
    stored_conv_id: str | None = None
    additional_context: str | None = None
    patient_data: dict | None = None
    section_classifications: dict | None = None

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper_id = task.paper_id
        patient_id = task.patient_id
        if patient_id is None:
            raise ValueError(
                f'Task {task_id}: PHENOTYPE_EXTRACTION requires patient_id'
            )

        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

        paper = session.get(PaperDB, paper_id)
        supplement_format = paper.supplement_format if paper else None
        section_classifications = paper.section_classifications if paper else None

        patient_row = session.get(PatientDB, patient_id)
        if not patient_row:
            return

        patient_data = {
            'patient_id': patient_row.id,
            'identifier': patient_row.identifier,
            'identifier_quote': patient_row.identifier_evidence['quote'],
        }

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
        agent = patient_phenotype_linking_agent
    else:
        # Initial query: build full message with paper + patient data + instructions
        paper_markdown = relevant_sections_md(
            paper_id, supplement_format, section_classifications
        )
        paper_context = format_paper_context(paper_markdown)
        message = (
            f'{paper_context}\n\n'
            f'Structured Patient JSON:\n{[patient_data]}\n\n'
            f'{PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS}'
        )
        agent = patient_phenotype_linking_agent

    result = await Runner.run(
        agent,
        message,
        conversation_id=stored_conv_id,
    )
    log_cache_metrics('PHENOTYPE_EXTRACTION', result)

    # Update DB with results
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_id = stored_conv_id

        # Idempotent: delete-then-insert
        # Phenotypes are scoped by patient_id, which is already run-versioned
        session.query(PhenotypeDB).filter(PhenotypeDB.patient_id == patient_id).delete()

        # Insert results
        for phenotype in result.final_output:
            # Ensure patient_id is set on the phenotype
            if phenotype.patient_id is None or phenotype.patient_id != patient_id:
                phenotype.patient_id = patient_id
            session.add(phenotype_to_db(paper_id, phenotype))


async def handle_hpo_linking(task_id: int) -> None:
    """Link a phenotype to HPO terms."""
    phenotype_id: int | None = None
    stored_conv_id: str | None = None
    additional_context: str | None = None
    phenotype_data: dict | None = None

    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        phenotype_id = task.phenotype_id
        if phenotype_id is None:
            raise ValueError(f'Task {task_id}: HPO_LINKING requires phenotype_id')

        stored_conv_id = task.conversation_id
        additional_context = task.additional_context

        phenotype_row = session.get(PhenotypeDB, phenotype_id)
        if not phenotype_row:
            return

        term_lookup = build_term_lookup()
        candidates = find_matching_hpo_terms(
            str(phenotype_row.concept), term_lookup=term_lookup
        )

        phenotype_data = {
            'phenotype_id': phenotype_row.id,
            'concept': phenotype_row.concept,
            'negated': phenotype_row.negated,
            'uncertain': phenotype_row.uncertain,
            'family_history': phenotype_row.family_history,
            'candidates': [c.model_dump() for c in candidates],
        }

    stored_conv_id = await ensure_conversation_id(stored_conv_id)

    if additional_context is not None:
        # Follow-up: agent has context from conversation
        message = build_followup_prompt(additional_context)
    else:
        # Initial query: build full message with phenotype data + instructions
        message = (
            f'Phenotype JSON:\n{json.dumps(phenotype_data, indent=2)}\n\n'
            f'{HPO_LINKING_AGENT_INSTRUCTIONS}'
        )

    result = await Runner.run(
        hpo_linking_agent,
        message,
        max_turns=15,
        conversation_id=stored_conv_id,
        run_config=RunConfig(
            trace_metadata={
                'paper_id': str(task_id),
                'phenotype_id': str(phenotype_id),
                'concept': phenotype_data['concept'],
            },
        ),
    )
    log_cache_metrics('HPO_LINKING', result)

    # Store results in new session
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_id = stored_conv_id

        # Idempotent: delete-then-insert
        session.query(HpoDB).filter(HpoDB.phenotype_id == phenotype_id).delete()
        session.add(hpo_to_db(phenotype_id, result.final_output))


TASK_HANDLERS: dict[TaskType, Callable[[int], Awaitable[None]]] = {
    TaskType.PDF_PARSING: handle_pdf_parsing,
    TaskType.PAPER_CLASSIFIER: handle_paper_section_classifier,
    TaskType.PAPER_METADATA: handle_paper_metadata,
    TaskType.VARIANT_EXTRACTION: handle_variant_extraction,
    TaskType.PEDIGREE_DESCRIPTION: handle_pedigree_description,
    TaskType.PATIENT_EXTRACTION: handle_patient_extraction,
    TaskType.SEGREGATION_EVIDENCE_EXTRACTION: handle_segregation_evidence_extraction,
    TaskType.SEGREGATION_ANALYSIS_COMPUTED: handle_segregation_analysis_computed,
    TaskType.VARIANT_HARMONIZATION: handle_variant_harmonization,
    TaskType.VARIANT_ANNOTATION: handle_variant_annotation,
    TaskType.PATIENT_VARIANT_LINKING: handle_patient_variant_linking,
    TaskType.PHENOTYPE_EXTRACTION: handle_phenotype_extraction,
    TaskType.HPO_LINKING: handle_hpo_linking,
}
