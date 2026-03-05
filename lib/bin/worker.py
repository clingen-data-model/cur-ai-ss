#!/usr/bin/env python3
import asyncio
import datetime
import json
import logging
import sys
import time
import traceback

from agents import Runner
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from lib.agents.paper_extraction_agent import PaperExtractionOutput
from lib.agents.paper_extraction_agent import agent as paper_extraction_agent
from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.agents.patient_variant_linking_agent import (
    agent as patient_variant_linking_agent,
)
from lib.agents.variant_enrichment_agent import (
    HarmonizedVariant,
    VariantEnrichmentOutput,
    enrich_variants_batch,
)
from lib.agents.variant_extraction_agent import agent as variant_extraction_agent
from lib.agents.variant_harmonization_agent import agent as variant_harmonization_agent
from lib.api.db import session_scope
from lib.evagg.pdf.parse import parse_content
from lib.models import PaperDB, PipelineStatus

LEASE_TIMEOUT_S = 900
POLL_INTERVAL_S = 10
RETRIES = 2

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(process)d] %(name)s: %(message)s",
    stream=sys.stdout,
)

async def parse_paper_task_async(paper_db: PaperDB) -> None:
    result = await Runner.run(
        paper_extraction_agent,
        f'Paper (fulltext md): {paper_db.fulltext_md}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.metadata_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.metadata_json_path, 'w') as f:
        f.write(json_response)
    _persist_paper_extraction(paper_db.id, result.final_output)


def _persist_paper_extraction(paper_id: str, output: PaperExtractionOutput) -> None:
    """Persist PaperExtractionOutput fields to the papers table."""
    with session_scope() as session:
        paper_db = session.get(PaperDB, paper_id)
        if paper_db:
            output.apply_to(paper_db)


async def parse_patients_task_async(paper_db: PaperDB) -> None:
    result = await Runner.run(
        patient_extraction_agent,
        f'Paper (fulltext md): {paper_db.fulltext_md}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.patient_info_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.patient_info_json_path, 'w') as f:
        f.write(json_response)


async def harmonize_variants_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.variants_json_path, 'r') as f:
        variants_output = json.load(f)

    result = await Runner.run(
        variant_harmonization_agent,
        f'Variants JSON:\n{json.dumps(variants_output, indent=2)}',
        max_turns=10 * len(variants_output['variants']),
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.harmonized_variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.harmonized_variants_json_path, 'w') as f:
        f.write(json_response)


async def extract_variants_task_async(paper_db: PaperDB, gene_symbol: str) -> None:
    result = await Runner.run(
        variant_extraction_agent,
        f'Gene Symbol: {gene_symbol}\nPaper (fulltext md): {paper_db.fulltext_md}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.variants_json_path, 'w') as f:
        f.write(json_response)


async def patient_variant_linking_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.variants_json_path, 'r') as f:
        variants_output = json.load(f)
    with open(paper_db.patient_info_json_path, 'r') as f:
        patients_output = json.load(f)

    structured_variants = [
        {
            'variant_id': idx,
            'variant_description_verbatim': variant['variant_description_verbatim'],
            'variant_evidence_context': variant['variant_evidence_context'],
        }
        for idx, variant in enumerate(variants_output['variants'], start=1)
    ]
    structured_patients = [
        {
            'patient_id': idx,
            'identifier': patient['identifier'],
            'identifier_evidence': patient['identifier_evidence'],
        }
        for idx, patient in enumerate(patients_output['patients'], start=1)
    ]
    result = await Runner.run(
        patient_variant_linking_agent,
        f'Variants JSON:\n{structured_variants}\n Patients JSON:\n {structured_patients}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.patient_variant_links_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.patient_variant_links_json_path, 'w') as f:
        f.write(json_response)


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


def initial_extraction(paper_id: str, gene_symbol: str) -> None:
    async def _run_extraction_pipeline(paper_db: PaperDB, gene_symbol: str) -> None:
        await asyncio.gather(
            parse_paper_task_async(paper_db),
            parse_patients_task_async(paper_db),
            extract_variants_task_async(paper_db, gene_symbol),
        )

    max_attempts = RETRIES + 1
    with session_scope() as session:
        session.execute(
            update(PaperDB)
            .where(PaperDB.id == paper_id)
            .values(pipeline_status=PipelineStatus.EXTRACTION_RUNNING)
        )
    for attempt in range(1, max_attempts + 1):
        try:
            paper_db = PaperDB(id=paper_id)
            parse_content(paper_db, force=True)
            asyncio.run(_run_extraction_pipeline(paper_db, gene_symbol))
            with session_scope() as session:
                session.execute(
                    update(PaperDB)
                    .where(PaperDB.id == paper_id)
                    .values(pipeline_status=PipelineStatus.EXTRACTION_COMPLETED)
                )
            logger.info(f'Extraction attempt {attempt}/{max_attempts} succeeded')
            return
        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
            raise
        except Exception:
            logger.exception(f'Extraction failed on attempt {attempt}')
            if attempt == max_attempts:
                with session_scope() as session:
                    session.execute(
                        update(PaperDB)
                        .where(PaperDB.id == paper_id)
                        .values(pipeline_status=PipelineStatus.EXTRACTION_FAILED)
                    )
                return


def linking_tasks(paper_id: str) -> None:
    async def _run_linking_pipeline(paper_db: PaperDB) -> None:
        await asyncio.gather(
            harmonize_variants_task_async(paper_db),
            patient_variant_linking_task_async(paper_db),
        )
        await enrich_variants_task_async(paper_db)

    max_attempts = RETRIES + 1
    with session_scope() as session:
        session.execute(
            update(PaperDB)
            .where(PaperDB.id == paper_id)
            .values(pipeline_status=PipelineStatus.LINKING_RUNNING)
        )
    for attempt in range(1, max_attempts + 1):
        try:
            paper_db = PaperDB(id=paper_id).with_content()
            asyncio.run(_run_linking_pipeline(paper_db))
            with session_scope() as session:
                session.execute(
                    update(PaperDB)
                    .where(PaperDB.id == paper_id)
                    .values(pipeline_status=PipelineStatus.COMPLETED)
                )
            logger.info(f'Attempt {attempt}/{max_attempts} succeeded')
            return
        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
            raise
        except Exception as e:
            logger.exception(f'Linking failed on attempt {attempt}')
            if attempt == max_attempts:
                with session_scope() as session:
                    session.execute(
                        update(PaperDB)
                        .where(PaperDB.id == paper_id)
                        .values(pipeline_status=PipelineStatus.LINKING_FAILED)
                    )
                return


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
                                PaperDB.last_modified < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.last_modified.asc())  # oldest first
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
                                PaperDB.last_modified < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.last_modified.asc())
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

        time.sleep(POLL_INTERVAL_S)


if __name__ == '__main__':
    main()
