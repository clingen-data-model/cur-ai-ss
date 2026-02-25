#!/usr/bin/env python3
import asyncio
import json
import logging
import time
import traceback

from agents import Runner
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from lib.agents.paper_extraction_agent import agent as paper_extraction_agent
from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.agents.variant_enrichment_agent import (
    HarmonizedVariant,
    VariantEnrichmentOutput,
    enrich_variants_batch,
)
from lib.agents.variant_extraction_agent import agent as variant_extraction_agent
from lib.agents.variant_harmonization_agent import agent as variant_harmonization_agent
from lib.api.db import session_scope
from lib.evagg.llm import OpenAIClient
from lib.evagg.pdf.parse import parse_content
from lib.evagg.ref import (
    NcbiLookupClient,
)
from lib.evagg.ref.ncbi import get_ncbi_response_translator
from lib.evagg.types.base import Paper
from lib.evagg.utils.web import RequestsWebContentClient, WebClientSettings
from lib.models import ExtractionStatus, PaperDB, PatientDB, VariantDB
from lib.models.converters import (
    paper_metadata_to_db,
    patient_info_to_db,
    variant_to_db,
)

POLL_INTERVAL_S = 10
RETRIES = 3

logger = logging.getLogger(__name__)


async def parse_paper_task_async(paper: Paper, paper_id: str) -> None:
    result = await Runner.run(
        paper_extraction_agent,
        f'Paper (fulltext md): {paper.fulltext_md}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper.metadata_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.metadata_json_path, 'w') as f:
        f.write(json_response)

    # Persist metadata to DB
    with session_scope() as session:
        paper_db = session.get(PaperDB, paper_id)
        if paper_db:
            paper_metadata_to_db(result.final_output, paper_db)


async def parse_patients_task_async(paper: Paper, paper_id: str) -> None:
    result = await Runner.run(
        patient_extraction_agent,
        f'Paper (fulltext md): {paper.fulltext_md}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper.patient_info_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.patient_info_json_path, 'w') as f:
        f.write(json_response)

    # Persist patients to DB
    with session_scope() as session:
        session.execute(delete(PatientDB).where(PatientDB.paper_id == paper_id))
        for patient in result.final_output.patients:
            session.add(patient_info_to_db(patient, paper_id))


async def harmonize_variants_task_async(paper: Paper) -> None:
    with open(paper.variants_json_path, 'r') as f:
        variants_output = json.load(f)

    result = await Runner.run(
        variant_harmonization_agent,
        f'Variants JSON:\n{json.dumps(variants_output, indent=2)}',
        max_turns=7 * len(variants_output['variants']),
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper.harmonized_variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.harmonized_variants_json_path, 'w') as f:
        f.write(json_response)


async def extract_variants_task_async(
    paper: Paper, gene_symbol: str, paper_id: str
) -> None:
    result = await Runner.run(
        variant_extraction_agent,
        f'Gene Symbol: {gene_symbol}\nPaper (fulltext md): {paper.fulltext_md}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper.variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.variants_json_path, 'w') as f:
        f.write(json_response)

    # Persist variants to DB
    with session_scope() as session:
        session.execute(delete(VariantDB).where(VariantDB.paper_id == paper_id))
        for variant in result.final_output.variants:
            session.add(variant_to_db(variant, paper_id))


async def enrich_variants_task_async(paper: Paper) -> None:
    with open(paper.harmonized_variants_json_path, 'r') as f:
        harmonized_data = json.load(f)
    harmonized_variants = [HarmonizedVariant(**v) for v in harmonized_data['variants']]
    # Offload blocking enrichment to thread
    enriched_variants = await asyncio.to_thread(
        enrich_variants_batch,
        harmonized_variants,
    )
    output = VariantEnrichmentOutput(variants=enriched_variants)
    paper.enriched_variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.enriched_variants_json_path, 'w') as f:
        f.write(output.model_dump_json(indent=2))


async def run_tasks_concurrently(paper: Paper, gene_symbol: str, paper_id: str) -> None:
    await asyncio.gather(
        parse_paper_task_async(paper, paper_id),
        parse_patients_task_async(paper, paper_id),
        extract_variants_task_async(paper, gene_symbol, paper_id),
    )
    # Runs after variants completes
    await harmonize_variants_task_async(paper)
    await enrich_variants_task_async(paper)


def initial_extraction(paper_db: PaperDB) -> None:
    max_attempts = RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            paper = Paper(id=paper_db.id).with_content()
            parse_content(paper, force=True)
            asyncio.run(
                run_tasks_concurrently(paper, paper_db.gene.symbol, paper_db.id)
            )
            paper_db.extraction_status = ExtractionStatus.PARSED
            logger.info(f'Attempt {attempt}/{max_attempts} succeeded')
            return
        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
            raise
        except Exception as e:
            logger.error(f'Error executing app on attempt {attempt}: {e}')
            logger.error(traceback.format_exc())
            if attempt == max_attempts:
                logger.error('All retries exhausted. Exiting.')
                raise


def main() -> None:
    while True:
        paper_db = None
        try:
            with session_scope() as session:
                paper_db = session.scalars(
                    select(PaperDB)
                    .options(joinedload(PaperDB.gene))
                    .where(PaperDB.extraction_status == ExtractionStatus.QUEUED)
                    .order_by(PaperDB.id)
                    .limit(1)
                ).first()
                if paper_db:
                    logger.info(f'Dequeued paper {paper_db.id}')
                    initial_extraction(paper_db)
        except KeyboardInterrupt:
            logger.info('Shutting down poller')
            break
        except SQLAlchemyError as e:
            logger.exception(f'Database error occurred')
            if paper_db:
                with session_scope() as session:
                    paper_db = session.merge(paper_db)
                    paper_db.extraction_status = ExtractionStatus.FAILED
        except Exception as e:
            logger.exception(f'An unexpected error occurred')
            if paper_db:
                with session_scope() as session:
                    paper_db = session.merge(paper_db)
                    paper_db.extraction_status = ExtractionStatus.FAILED
        time.sleep(POLL_INTERVAL_S)
        logger.info('waiting for work')


if __name__ == '__main__':
    main()
