#!/usr/bin/env python3
import asyncio
import datetime
import json
import logging
import time
import traceback
from typing import Callable

from agents import Runner
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

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
from lib.agents.variant_enrichment_agent import (
    HarmonizedVariant,
    VariantEnrichmentOutput,
    enrich_variants_batch,
)
from lib.agents.variant_extraction_agent import (
    agent as variant_extraction_agent,
)
from lib.agents.variant_harmonization_agent import agent as variant_harmonization_agent
from lib.api.db import session_scope
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import fulltext_md, pdf_image_caption_path, pdf_image_path
from lib.models import (
    ExtractedVariantDB,
    PaperDB,
    PatientDB,
    PedigreeDB,
    PipelineStatus,
)
from lib.models.converters import (
    hpo_to_db,
    patient_to_db,
    pedigree_to_db,
    phenotype_to_db,
    variant_to_db,
)
from lib.models.phenotype import ExtractedPhenotypeDB, HpoCandidate, HpoDB
from lib.models.variant import ExtractedVariant
from lib.reference_data.hpo import build_term_lookup, find_matching_hpo_terms

LEASE_TIMEOUT_S = 900
POLL_INTERVAL_S = 10
RETRIES = 2

setup_logging()
logger = logging.getLogger(__name__)


def run_with_retries(
    paper_id: str,
    run_fn: Callable,
    running_status: PipelineStatus,
    success_status: PipelineStatus,
    failure_status: PipelineStatus,
) -> None:
    max_attempts = RETRIES + 1

    with session_scope() as session:
        session.execute(
            update(PaperDB)
            .where(PaperDB.id == paper_id)
            .values(pipeline_status=running_status)
        )

    for attempt in range(1, max_attempts + 1):
        try:
            run_fn()

            with session_scope() as session:
                session.execute(
                    update(PaperDB)
                    .where(PaperDB.id == paper_id)
                    .values(pipeline_status=success_status)
                )

            logger.info(f'Attempt {attempt}/{max_attempts} succeeded')
            return

        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
            raise

        except Exception:
            logger.exception(f'Attempt {attempt} failed')

            if attempt == max_attempts:
                with session_scope() as session:
                    session.execute(
                        update(PaperDB)
                        .where(PaperDB.id == paper_id)
                        .values(pipeline_status=failure_status)
                    )
                return


async def parse_paper_task_async(paper_id: str) -> None:
    result = await Runner.run(
        paper_extraction_agent,
        f'Paper (fulltext md): {fulltext_md(paper_id)}',
    )
    with session_scope() as session:
        fetched_paper = session.get(PaperDB, paper_id)
        if not fetched_paper:
            return None
        result.final_output.apply_to(fetched_paper)


async def parse_patients_task_async(paper_db: PaperDB) -> None:
    # Load pedigree from DB
    with session_scope() as session:
        pedigree_row = (
            session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_db.id).first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

    result = await Runner.run(
        patient_extraction_agent,
        f'Paper (fulltext md): {fulltext_md(paper_db.id)} Pedigree Description: \n {pedigree_descriptions_output}',
    )

    # Persist patients to DB (idempotent: delete-then-insert)
    with session_scope() as session:
        session.query(PatientDB).filter(PatientDB.paper_id == paper_db.id).delete()
        for patient_index, patient_info in enumerate(
            result.final_output.patients, start=1
        ):
            session.add(patient_to_db(paper_db.id, patient_index, patient_info))


async def harmonize_variants_task_async(paper_db: PaperDB) -> None:
    with session_scope() as session:
        rows = (
            session.query(ExtractedVariantDB)
            .filter(ExtractedVariantDB.paper_id == paper_db.id)
            .order_by(ExtractedVariantDB.variant_idx)
            .all()
        )
        variants_output = {
            'variants': [
                ExtractedVariant(
                    **{f: getattr(r, f) for f in ExtractedVariant.model_fields}
                )
                for r in rows
            ]
        }

    result = await Runner.run(
        variant_harmonization_agent,
        f'Variants JSON:\n{json.dumps(variants_output, indent=2)}',
        max_turns=10 * len(variants_output['variants']),
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.harmonized_variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.harmonized_variants_json_path, 'w') as f:
        f.write(json_response)


async def extract_variants_task_async(paper_id: str, gene_symbol: str) -> None:
    result = await Runner.run(
        variant_extraction_agent,
        f'Gene Symbol: {gene_symbol}\nPaper (fulltext md): {fulltext_md(paper_id)}',
    )
    with session_scope() as session:
        session.query(ExtractedVariantDB).filter(
            ExtractedVariantDB.paper_id == paper_id
        ).delete()
        for idx, variant in enumerate(result.final_output.variants, start=1):
            session.add(variant_to_db(paper_id, idx, variant))


async def pedigree_describer_task_async(paper_id: str) -> None:
    image_id, combined_text = 0, ''
    while True:
        pdf_image = pdf_image_path(paper_id, image_id)
        if not pdf_image.exists():
            break
        caption_path = pdf_image_caption_path(paper_id, image_id)
        caption_text = (
            caption_path.read_text() if caption_path.exists() else 'No caption'
        )
        image_url = f'{env.PROTOCOL}{env.API_ENDPOINT}{pdf_image}'
        combined_text += f'[Processing Pipeline Figure {image_id}]\n'
        combined_text += f'URL: {image_url}\n'
        combined_text += f'Caption: {caption_text}\n\n'
        image_id += 1
    result = await Runner.run(
        pedigree_describer_agent,
        combined_text,
    )
    # Persist pedigree to DB (idempotent: delete-then-insert)
    # Only insert if pedigree was found
    with session_scope() as session:
        session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).delete()
        if result.final_output and result.final_output.found:
            session.add(pedigree_to_db(paper_id, result.final_output))


async def patient_variant_linking_task_async(paper_db: PaperDB) -> None:
    with session_scope() as session:
        variant_rows = (
            session.query(ExtractedVariantDB)
            .filter(ExtractedVariantDB.paper_id == paper_db.id)
            .order_by(ExtractedVariantDB.variant_idx)
            .all()
        )
    structured_variants = [
        {
            'variant_id': r.variant_idx,
            'variant_quote': r.variant_evidence['quote'],
        }
        for r in variant_rows
    ]
    with session_scope() as session:
        patient_rows = (
            session.query(PatientDB)
            .filter(PatientDB.paper_id == paper_db.id)
            .order_by(PatientDB.patient_idx)
            .all()
        )
        structured_patients = [
            {
                'patient_idx': p.patient_idx,
                'identifier': p.identifier,
                'identifier_quote': p.identifier_evidence['quote'],
            }
            for p in patient_rows
        ]
        # Load pedigree from DB
        pedigree_row = (
            session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_db.id).first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

    result = await Runner.run(
        patient_variant_linking_agent,
        f'Variants JSON:\n{structured_variants}\n Patients JSON:\n {structured_patients} Pedigree Description: \n {pedigree_descriptions_output} Paper (fulltext md): {fulltext_md(paper_db.id)}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.patient_variant_links_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.patient_variant_links_json_path, 'w') as f:
        f.write(json_response)


async def patient_phenotype_linking_task_async(paper_db: PaperDB) -> None:
    with session_scope() as session:
        patient_rows = (
            session.query(PatientDB)
            .filter(PatientDB.paper_id == paper_db.id)
            .order_by(PatientDB.patient_idx)
            .all()
        )
        structured_patients = [
            {
                'patient_idx': p.patient_idx,
                'identifier': p.identifier,
                'identifier_quote': p.identifier_evidence['quote'],
            }
            for p in patient_rows
        ]
    result = await Runner.run(
        patient_phenotype_linking_agent,
        f'Paper (fulltext md): {fulltext_md(paper_db.id)}\n\nStructured Patients JSON:\n{structured_patients}',
    )

    # Persist extracted phenotypes to DB (idempotent: delete-then-insert)
    with session_scope() as session:
        session.query(ExtractedPhenotypeDB).filter(
            ExtractedPhenotypeDB.paper_id == paper_db.id
        ).delete()
        for idx, phenotype in enumerate(
            result.final_output.extracted_phenotypes, start=1
        ):
            session.add(phenotype_to_db(paper_db.id, idx, phenotype))


async def enrich_variants_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.harmonized_variants_json_path, 'r') as f:
        harmonized_data = json.load(f)
    harmonized_variants = [HarmonizedVariant(**v) for v in harmonized_data['variants']]
    # Offload blocking enrichment to thread
    enriched_variants = await asyncio.to_thread(
        enrich_variants_batch,
        harmonized_variants,
    )
    output = VariantEnrichmentOutput(variants=enriched_variants)
    paper_db.enriched_variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.enriched_variants_json_path, 'w') as f:
        f.write(output.model_dump_json(indent=2))


async def hpo_linking_task_async(paper_db: PaperDB) -> None:
    with session_scope() as session:
        phenotype_rows = (
            session.query(ExtractedPhenotypeDB)
            .filter(ExtractedPhenotypeDB.paper_id == paper_db.id)
            .order_by(
                ExtractedPhenotypeDB.patient_idx, ExtractedPhenotypeDB.phenotype_idx
            )
            .all()
        )

    term_lookup = build_term_lookup()

    phenotype_inputs = []
    for row in phenotype_rows:
        candidates: list[HpoCandidate] = find_matching_hpo_terms(
            row.concept, term_lookup=term_lookup
        )
        phenotype_inputs.append(
            {
                'phenotype_idx': row.phenotype_idx,
                'concept': row.concept,
                'negated': row.negated,
                'uncertain': row.uncertain,
                'family_history': row.family_history,
                'candidates': [c.model_dump() for c in candidates],
            }
        )

    result = await Runner.run(
        hpo_linking_agent,
        f'Phenotypes JSON:\n{json.dumps(phenotype_inputs, indent=2)}',
        max_turns=5 * len(phenotype_inputs),
    )

    # Build lookup: phenotype_idx → DB row
    row_lookup = {r.phenotype_idx: r for r in phenotype_rows}

    # Persist HPO links to DB (idempotent: delete-then-insert)
    with session_scope() as session:
        session.query(HpoDB).filter(HpoDB.paper_id == paper_db.id).delete()
        for link in result.final_output.links:
            row = row_lookup[link.phenotype_idx]
            if row:
                session.add(
                    hpo_to_db(paper_db.id, row.patient_idx, row.phenotype_idx, link.hpo)
                )


def initial_extraction(paper_id: str, gene_symbol: str) -> None:
    def run() -> None:
        async def _run1() -> None:
            await asyncio.gather(
                parse_paper_task_async(paper_id),
                extract_variants_task_async(paper_id, gene_symbol),
                pedigree_describer_task_async(paper_id),
            )

        paper_db = PaperDB(id=paper_id).with_content()

        async def _run2() -> None:
            await asyncio.gather(
                parse_patients_task_async(paper_db),
            )

        parse_content(paper_id, force=True)
        asyncio.run(_run1())
        asyncio.run(_run2())

    run_with_retries(
        paper_id=paper_id,
        run_fn=run,
        running_status=PipelineStatus.EXTRACTION_RUNNING,
        success_status=PipelineStatus.EXTRACTION_COMPLETED,
        failure_status=PipelineStatus.EXTRACTION_FAILED,
    )


def linking_tasks(paper_id: str) -> None:
    def run() -> None:
        async def _run() -> None:
            paper_db = PaperDB(id=paper_id).with_content()

            await asyncio.gather(
                harmonize_variants_task_async(paper_db),
                patient_variant_linking_task_async(paper_db),
                patient_phenotype_linking_task_async(paper_db),
            )

            await asyncio.gather(
                enrich_variants_task_async(paper_db),
                hpo_linking_task_async(paper_db),
            )

        asyncio.run(_run())

    run_with_retries(
        paper_id=paper_id,
        run_fn=run,
        running_status=PipelineStatus.LINKING_RUNNING,
        success_status=PipelineStatus.COMPLETED,
        failure_status=PipelineStatus.LINKING_FAILED,
    )


def main() -> None:
    while True:
        try:
            now = datetime.datetime.utcnow()
            expired_cutoff = now - datetime.timedelta(seconds=LEASE_TIMEOUT_S)
            with session_scope() as session:
                # Extraction queue
                extraction_job = session.scalars(
                    select(PaperDB)
                    .where(
                        or_(
                            PaperDB.pipeline_status == PipelineStatus.QUEUED,
                            and_(
                                PaperDB.pipeline_status
                                == PipelineStatus.EXTRACTION_RUNNING,
                                PaperDB.updated_at < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.updated_at.asc())  # oldest first
                    .limit(1)
                ).first()

                if extraction_job:
                    paper_id = extraction_job.id
                    gene_symbol = extraction_job.gene.symbol
                    logger.info(f'Dequeued paper {paper_id} for extraction')

            if extraction_job:
                initial_extraction(paper_id, gene_symbol)
                continue  # restart loop immediately

            with session_scope() as session:
                # Linking queue
                linking_job = session.scalars(
                    select(PaperDB)
                    .where(
                        or_(
                            PaperDB.pipeline_status
                            == PipelineStatus.EXTRACTION_COMPLETED,
                            and_(
                                PaperDB.pipeline_status
                                == PipelineStatus.LINKING_RUNNING,
                                PaperDB.updated_at < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.updated_at.asc())
                    .limit(1)
                ).first()

                if linking_job:
                    paper_id = linking_job.id
                    logger.info(f'Dequeued paper {paper_id} for linking')

            if linking_job:
                linking_tasks(paper_id)
                continue

        except KeyboardInterrupt:
            logger.info('Shutting down poller')
            break

        except Exception:
            logger.exception('Unexpected error in poller loop')

        logger.info('Looking for work')
        time.sleep(POLL_INTERVAL_S)


if __name__ == '__main__':
    main()
