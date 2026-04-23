import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Union

from agents import RunConfig, Runner
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from lib.agents.hpo_linking_agent import agent as hpo_linking_agent
from lib.agents.paper_extraction_agent import agent as paper_extraction_agent
from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.agents.patient_phenotype_linking_agent import (
    agent as patient_phenotype_linking_agent,
)
from lib.agents.patient_variant_linking_agent import (
    agent as patient_variant_linking_agent,
)
from lib.agents.pedigree_describer_agent import agent as pedigree_describer_agent
from lib.agents.segregation_analysis_computed_agent import (
    agent as segregation_analysis_computed_agent,
)
from lib.agents.segregation_evidence_extractor import (
    agent as segregation_evidence_extractor,
)
from lib.agents.variant_enrichment_agent import enrich_variants_batch
from lib.agents.variant_extraction_agent import (
    agent as variant_extraction_agent,
)
from lib.agents.variant_harmonization_agent import agent as variant_harmonization_agent
from lib.api.db import session_scope
from lib.core.environment import env
from lib.misc.gcs import upload_and_sign_image
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import fulltext_md, pdf_image_caption_path, pdf_image_path
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
from lib.models.phenotype import HPOTerm
from lib.models.variant import HarmonizedVariant, Variant
from lib.reference_data.hpo import build_term_lookup, find_matching_hpo_terms
from lib.tasks.models import TaskType

logger = logging.getLogger(__name__)


async def get_or_create_conversation(conversation_id: str | None) -> str:
    """Get existing conversation or create a new one.

    Args:
        conversation_id: Existing conversation ID, or None to create new

    Returns:
        The conversation ID (either provided or newly created)
    """
    if conversation_id:
        return conversation_id

    client = AsyncOpenAI(api_key=env.OPENAI_API_KEY)
    conversation = await client.conversations.create()
    return conversation.id


def handle_pdf_parsing(task_id: int) -> None:
    """Parse PDF to markdown and extract images/tables."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return
        parse_content(task.paper_id, force=True)


async def handle_paper_metadata(task_id: int) -> None:
    """Extract paper metadata (title, authors, abstract, etc)."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        conv_id = await get_or_create_conversation(task.conversation_ids.get('default'))
        result = await Runner.run(
            paper_extraction_agent,
            f'Gene: {paper.gene.symbol}\n\nPaper (fulltext md): {fulltext_md(task.paper_id)}',
            conversation_id=conv_id,
        )

        task.conversation_ids['default'] = conv_id
        paper = session.get(PaperDB, task.paper_id)
        if paper:
            result.final_output.apply_to(paper)


async def handle_variant_extraction(task_id: int) -> None:
    """Extract genetic variants from paper."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        result = await Runner.run(
            variant_extraction_agent,
            f'Gene Symbol: {paper.gene.symbol}\nPaper (fulltext md): {fulltext_md(task.paper_id)}',
        )

        # Idempotent: delete-then-insert
        session.query(VariantDB).filter(VariantDB.paper_id == task.paper_id).delete()
        for variant in result.final_output.variants:
            session.add(variant_to_db(task.paper_id, variant))


async def handle_pedigree_description(task_id: int) -> None:
    """Describe pedigree images from paper."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        image_id, combined_text = 0, ''
        while True:
            pdf_image = pdf_image_path(task.paper_id, image_id)
            if not pdf_image.exists():
                break
            caption_path = pdf_image_caption_path(task.paper_id, image_id)
            caption_text = (
                caption_path.read_text() if caption_path.exists() else 'No caption'
            )
            # Upload image to GCS and get signed URL
            logger.info(f'Processing image {image_id} from {pdf_image}')
            image_url = upload_and_sign_image(task.paper_id, image_id, pdf_image)
            logger.info(
                f'Image {image_id} URL type: {type(image_url)}, starts with: {image_url[:50] if image_url else "None"}'
            )
            combined_text += f'[Processing Pipeline Figure {image_id}]\n'
            combined_text += f'URL: {image_url}\n'
            combined_text += f'Caption: {caption_text}\n\n'
            image_id += 1

        conv_id = await get_or_create_conversation(task.conversation_ids.get('default'))
        result = await Runner.run(
            pedigree_describer_agent,
            combined_text,
            conversation_id=conv_id,
        )

        task.conversation_ids['default'] = conv_id
        # Idempotent: delete-then-insert
        session.query(PedigreeDB).filter(PedigreeDB.paper_id == task.paper_id).delete()
        if result.final_output and result.final_output.found:
            session.add(pedigree_to_db(task.paper_id, result.final_output))


async def handle_patient_extraction(task_id: int) -> None:
    """Extract patient information from paper."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        # Load pedigree from DB
        pedigree_row = (
            session.query(PedigreeDB)
            .filter(PedigreeDB.paper_id == task.paper_id)
            .first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

        conv_id = await get_or_create_conversation(task.conversation_ids.get('default'))
        result = await Runner.run(
            patient_extraction_agent,
            f'Paper (fulltext md): {fulltext_md(task.paper_id)}\nPedigree Description: \n {pedigree_descriptions_output}',
            conversation_id=conv_id,
        )

        task.conversation_ids['default'] = conv_id
        # Idempotent: delete families (CASCADE deletes patients), then re-insert both
        session.query(FamilyDB).filter(FamilyDB.paper_id == task.paper_id).delete()
        session.flush()

        # Insert families first so we have family IDs for patient assignment
        family_entries_by_id: dict[str, int] = {}
        for entry in result.final_output.families:
            db_family = family_to_db(task.paper_id, entry.family)
            session.add(db_family)
            session.flush()
            family_entries_by_id[entry.family.identifier.value] = db_family.id

        # Insert patients with family assignments
        for patient_info in result.final_output.patients:
            db_patient = patient_to_db(task.paper_id, patient_info)
            # Use family_identifier from patient to find correct family
            family_id_value = patient_info.family_identifier.value
            if family_id_value in family_entries_by_id:
                db_patient.family_id = family_entries_by_id[family_id_value]
                db_patient.family_assignment_evidence = (
                    patient_info.family_identifier.model_dump()
                )
            session.add(db_patient)


async def handle_segregation_evidence_extraction(task_id: int) -> None:
    """Extract segregation evidence from paper for family/families."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        # Determine which families to process
        if task.family_id:
            families = (
                session.query(FamilyDB).filter(FamilyDB.id == task.family_id).all()
            )
        else:
            families = (
                session.query(FamilyDB).filter(FamilyDB.paper_id == task.paper_id).all()
            )

        if not families:
            return

        conv_id = await get_or_create_conversation(task.conversation_ids.get('default'))

        for family in families:
            # Load patients in family
            patients = (
                session.query(PatientDB).filter(PatientDB.family_id == family.id).all()
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

            result = await Runner.run(
                segregation_evidence_extractor,
                f'Paper (fulltext md): {fulltext_md(task.paper_id)}\n\nFamily Structure: {json.dumps(family_info, indent=2, default=str)}',
                conversation_id=conv_id,
            )

            # Delete existing segregation evidence and insert new
            session.query(SegregationEvidenceDB).filter(
                SegregationEvidenceDB.family_id == family.id
            ).delete()
            session.flush()

            # Convert and insert
            db_evidence = segregation_evidence_to_db(family.id, result.final_output)
            session.add(db_evidence)

        task.conversation_ids['default'] = conv_id


async def handle_segregation_analysis_computed(task_id: int) -> None:
    """Compute segregation analysis metrics for family/families using ClinGen methodology."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        # Determine which families to process
        if task.family_id:
            families = (
                session.query(FamilyDB).filter(FamilyDB.id == task.family_id).all()
            )
        else:
            families = (
                session.query(FamilyDB).filter(FamilyDB.paper_id == task.paper_id).all()
            )

        if not families:
            return

        conv_id = await get_or_create_conversation(task.conversation_ids.get('default'))

        for family in families:
            # Load patients in family
            patients = (
                session.query(PatientDB).filter(PatientDB.family_id == family.id).all()
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
                .filter(SegregationEvidenceDB.family_id == family.id)
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
                    }
                    for vl in variant_links
                ],
                'segregation_evidence': {
                    'extracted_lod_score': seg_evidence.extracted_lod_score
                    if seg_evidence
                    else None,
                    'sequencing_methodology': seg_evidence.sequencing_methodology
                    if seg_evidence
                    else None,
                    'has_unexplainable_non_segregations': seg_evidence.has_unexplainable_non_segregations
                    if seg_evidence
                    else None,
                }
                if seg_evidence
                else None,
            }

            result = await Runner.run(
                segregation_analysis_computed_agent,
                f'Paper (fulltext md): {fulltext_md(task.paper_id)}\n\nFamily Structure and Data: {json.dumps(family_info, indent=2, default=str)}',
                conversation_id=conv_id,
            )

            # Delete existing computed analysis and insert new
            session.query(SegregationAnalysisComputedDB).filter(
                SegregationAnalysisComputedDB.family_id == family.id
            ).delete()
            session.flush()

            # Convert and insert
            db_computed = segregation_analysis_computed_to_db(
                family.id, result.final_output
            )
            session.add(db_computed)

        task.conversation_ids['default'] = conv_id


async def handle_variant_harmonization(task_id: int) -> None:
    """Harmonize variants to standard genomic coordinates."""
    stored_conversation_ids: dict[str, str] = {}
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        stored_conversation_ids = {
            str(k): v for k, v in task.conversation_ids.items() if str(k).isdigit()
        }

        paper = session.get(PaperDB, task.paper_id)
        if not paper:
            return

        # Query variants to harmonize
        query = session.query(VariantDB).filter(VariantDB.paper_id == task.paper_id)
        if task.variant_id is not None:
            query = query.filter(VariantDB.id == task.variant_id)

        rows = query.order_by(VariantDB.id).all()

        # Extract variant payloads
        variant_payloads = [
            (
                row.id,
                {
                    'gene_symbol': paper.gene.symbol,
                    **{f: getattr(row, f) for f in Variant.model_fields},
                },
            )
            for row in rows
        ]

    sem = asyncio.Semaphore(2)
    conversation_ids: dict[int, str] = {}

    async def harmonize_single_variant(
        variant_id: int, variant_input: dict
    ) -> tuple[int, ReasoningBlock[HarmonizedVariant]]:
        async with sem:
            conv_id = await get_or_create_conversation(
                stored_conversation_ids.get(str(variant_id))
            )
            conversation_ids[variant_id] = conv_id
            result = await Runner.run(
                variant_harmonization_agent,
                f'Variant JSON:\n{json.dumps(variant_input, indent=2)}',
                max_turns=15,
                conversation_id=conv_id,
            )
            return variant_id, result.final_output

    results = await asyncio.gather(
        *[
            harmonize_single_variant(variant_id, variant_input)
            for variant_id, variant_input in variant_payloads
        ]
    )

    # Update DB with results
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_ids.update(conversation_ids)
        # Idempotent: delete-then-insert
        delete_query = session.query(HarmonizedVariantDB).filter(
            HarmonizedVariantDB.variant_id.in_(
                select(VariantDB.id).where(VariantDB.paper_id == task.paper_id)
            )
        )
        if task.variant_id is not None:
            delete_query = delete_query.filter(
                HarmonizedVariantDB.variant_id == task.variant_id
            )
        delete_query.delete()

        for variant_id, harmonized_output in results:
            session.add(harmonized_variant_to_db(variant_id, harmonized_output))


async def handle_variant_enrichment(task_id: int) -> None:
    """Enrich harmonized variants with annotations."""
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        query = (
            session.query(HarmonizedVariantDB)
            .join(VariantDB, HarmonizedVariantDB.variant_id == VariantDB.id)
            .filter(VariantDB.paper_id == task.paper_id)
        )
        if task.variant_id is not None:
            query = query.filter(HarmonizedVariantDB.variant_id == task.variant_id)

        rows = query.order_by(VariantDB.id).all()
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
        harmonized_variant_ids = [r.id for r in rows]

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

        # Idempotent: delete-then-insert
        delete_query = session.query(EnrichedVariantDB).filter(
            EnrichedVariantDB.harmonized_variant_id.in_(
                select(HarmonizedVariantDB.id)
                .join(VariantDB, HarmonizedVariantDB.variant_id == VariantDB.id)
                .where(VariantDB.paper_id == task.paper_id)
            )
        )
        if task.variant_id is not None:
            delete_query = delete_query.filter(
                EnrichedVariantDB.harmonized_variant_id.in_(
                    select(HarmonizedVariantDB.id).where(
                        HarmonizedVariantDB.variant_id == task.variant_id
                    )
                )
            )
        delete_query.delete()

        for hv_id, ev in zip(harmonized_variant_ids, enriched_variants):
            session.add(
                EnrichedVariantDB(
                    harmonized_variant_id=hv_id,
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
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        variant_rows = (
            session.query(VariantDB)
            .filter(VariantDB.paper_id == task.paper_id)
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
            .filter(PatientDB.paper_id == task.paper_id)
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
            session.query(PedigreeDB)
            .filter(PedigreeDB.paper_id == task.paper_id)
            .first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

        conv_id = await get_or_create_conversation(task.conversation_ids.get('default'))
        result = await Runner.run(
            patient_variant_linking_agent,
            f'Variants JSON:\n{structured_variants}\n Patients JSON:\n {structured_patients} Pedigree Description: \n {pedigree_descriptions_output} Paper (fulltext md): {fulltext_md(task.paper_id)}',
            conversation_id=conv_id,
        )

        task.conversation_ids['default'] = conv_id
        # Idempotent: delete-then-insert
        session.query(PatientVariantLinkDB).filter(
            PatientVariantLinkDB.paper_id == task.paper_id
        ).delete()
        for link in result.final_output.links:
            session.add(patient_variant_link_to_db(task.paper_id, link))


async def handle_phenotype_extraction(task_id: int) -> None:
    """Extract phenotypes for patients in paper.

    If task.patient_id is set, extract for only that patient.
    Otherwise, extract for all patients in the paper in parallel.
    """
    # Fetch all patients to process
    stored_conversation_ids: dict[str, str] = {}
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        paper_id = task.paper_id
        patient_id = task.patient_id
        stored_conversation_ids = dict(task.conversation_ids)
        query = session.query(PatientDB).filter(PatientDB.paper_id == paper_id)
        if patient_id is not None:
            query = query.filter(PatientDB.id == patient_id)

        patient_rows = query.order_by(PatientDB.id).all()
        patient_data_list = [
            {
                'patient_id': p.id,
                'identifier': p.identifier,
                'identifier_quote': p.identifier_evidence['quote'],
            }
            for p in patient_rows
        ]

    # Process patients in parallel with stored or fresh conversations
    sem = asyncio.Semaphore(2)
    conversation_ids: dict[int, str] = {}

    async def extract_phenotypes_for_patient(
        patient_data: dict,
    ) -> tuple[int, list]:
        async with sem:
            conv_id = await get_or_create_conversation(
                stored_conversation_ids.get(str(patient_data['patient_id']))
            )
            conversation_ids[patient_data['patient_id']] = conv_id
            result = await Runner.run(
                patient_phenotype_linking_agent,
                f'Paper (fulltext md): {fulltext_md(paper_id)}\n\nStructured Patient JSON:\n{[patient_data]}',
                conversation_id=conv_id,
            )
            return patient_data['patient_id'], result.final_output

    results = await asyncio.gather(
        *[extract_phenotypes_for_patient(p) for p in patient_data_list]
    )

    # Update DB with results
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_ids.update(conversation_ids)
        # Idempotent: delete-then-insert
        delete_query = session.query(PhenotypeDB).filter(
            PhenotypeDB.paper_id == paper_id
        )
        if patient_id is not None:
            delete_query = delete_query.filter(PhenotypeDB.patient_id == patient_id)
        delete_query.delete()

        # Insert all results
        for patient_id, phenotypes in results:
            for phenotype in phenotypes:
                # Ensure patient_id is set on the phenotype
                if phenotype.patient_id is None or phenotype.patient_id != patient_id:
                    phenotype.patient_id = patient_id
                session.add(phenotype_to_db(paper_id, phenotype))


async def handle_hpo_linking(task_id: int) -> None:
    """Link phenotypes to HPO terms."""
    stored_conversation_ids: dict[str, str] = {}
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        stored_conversation_ids = dict(task.conversation_ids)
        # Get phenotypes for this paper (optionally filtered by patient or phenotype)
        query = session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == task.paper_id)
        if task.patient_id is not None:
            query = query.filter(PhenotypeDB.patient_id == task.patient_id)
        if task.phenotype_id is not None:
            query = query.filter(PhenotypeDB.id == task.phenotype_id)

        phenotype_rows = query.order_by(PhenotypeDB.patient_id, PhenotypeDB.id).all()
        phenotype_id_set = {row.id for row in phenotype_rows}

        term_lookup = build_term_lookup()

        phenotype_inputs = []
        for row in phenotype_rows:
            candidates = find_matching_hpo_terms(
                str(row.concept), term_lookup=term_lookup
            )
            phenotype_inputs.append(
                {
                    'phenotype_id': row.id,
                    'concept': row.concept,
                    'negated': row.negated,
                    'uncertain': row.uncertain,
                    'family_history': row.family_history,
                    'candidates': [c.model_dump() for c in candidates],
                }
            )

    sem = asyncio.Semaphore(10)
    conversation_ids: dict[int, str] = {}

    async def link_phenotype_to_hpo(
        phenotype_data: dict,
    ) -> ReasoningBlock[HPOTerm]:
        async with sem:
            conv_id = await get_or_create_conversation(
                stored_conversation_ids.get(str(phenotype_data['phenotype_id']))
            )
            conversation_ids[phenotype_data['phenotype_id']] = conv_id
            result = await Runner.run(
                hpo_linking_agent,
                f'Phenotype JSON:\n{json.dumps(phenotype_data, indent=2)}',
                max_turns=15,
                conversation_id=conv_id,
                run_config=RunConfig(
                    trace_metadata={
                        'paper_id': str(task_id),
                        'phenotype_id': str(phenotype_data['phenotype_id']),
                        'concept': phenotype_data['concept'],
                    },
                ),
            )
            return result.final_output

    results = await asyncio.gather(
        *[link_phenotype_to_hpo(phenotype_data) for phenotype_data in phenotype_inputs]
    )

    # Store results in new session
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return

        task.conversation_ids.update(conversation_ids)
        # Idempotent: delete-then-insert
        session.query(HpoDB).filter(HpoDB.phenotype_id.in_(phenotype_id_set)).delete()

        for phenotype_data, hpo_reasoning in zip(phenotype_inputs, results):
            phenotype_id: int = phenotype_data['phenotype_id']  # type: ignore
            if phenotype_id in phenotype_id_set:
                session.add(hpo_to_db(phenotype_id, hpo_reasoning))


TASK_HANDLERS: dict[
    TaskType, Union[Callable[[int], Awaitable[None]], Callable[[int], None]]
] = {
    TaskType.PDF_PARSING: handle_pdf_parsing,
    TaskType.PAPER_METADATA: handle_paper_metadata,
    TaskType.VARIANT_EXTRACTION: handle_variant_extraction,
    TaskType.PEDIGREE_DESCRIPTION: handle_pedigree_description,
    TaskType.PATIENT_EXTRACTION: handle_patient_extraction,
    TaskType.SEGREGATION_EVIDENCE_EXTRACTION: handle_segregation_evidence_extraction,
    TaskType.SEGREGATION_ANALYSIS_COMPUTED: handle_segregation_analysis_computed,
    TaskType.VARIANT_HARMONIZATION: handle_variant_harmonization,
    TaskType.VARIANT_ENRICHMENT: handle_variant_enrichment,
    TaskType.PATIENT_VARIANT_LINKING: handle_patient_variant_linking,
    TaskType.PHENOTYPE_EXTRACTION: handle_phenotype_extraction,
    TaskType.HPO_LINKING: handle_hpo_linking,
}
