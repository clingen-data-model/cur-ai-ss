#!/usr/bin/env python3
import asyncio
import json
import logging
import time
import traceback

from agents import Runner
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.agents.variant_extraction_agent import agent as variant_extraction_agent
from lib.api.db import session_scope
from lib.evagg.llm import OpenAIClient
from lib.evagg.pdf.parse import parse_content
from lib.evagg.ref import (
    NcbiLookupClient,
)
from lib.evagg.ref.ncbi import get_ncbi_response_translator
from lib.evagg.types.base import Paper
from lib.evagg.utils.web import RequestsWebContentClient, WebClientSettings
from lib.models import ExtractionStatus, PaperDB

POLL_INTERVAL_S = 10
RETRIES = 3

logger = logging.getLogger(__name__)


def parse_paper_metadata_task(paper: Paper) -> Paper:
    llm_client = OpenAIClient()
    ncbi_lookup_client = NcbiLookupClient(
        web_client=RequestsWebContentClient(
            WebClientSettings(status_code_translator=get_ncbi_response_translator())
        )
    )
    title = asyncio.run(
        llm_client.prompt_json_from_string(
            user_prompt=f"""
            Extract the title of the following (truncated to 1000 characters) scientific paper.

            Return your response as a JSON object like this:
            {{
                "title": "The title of the paper"
            }}

            Paper: {paper.fulltext_md[:1000]}
        """,
        )
    )['title']
    pmids = ncbi_lookup_client.search(
        title + '[ti]',
    )
    if pmids:
        paper = ncbi_lookup_client.fetch(pmids[0], paper)

    # Dump the paper metadata
    paper.metadata_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.metadata_json_path, 'w') as f:
        json.dump({k: v for k, v in paper.__dict__.items() if k != 'content'}, f)
    return paper


async def parse_patients_task_async(paper: Paper) -> None:
    result = await Runner.run(
        patient_extraction_agent,
        f"Paper (fulltext md): {paper.fulltext_md}",
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper.patient_info_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.patient_info_json_path, "w") as f:
        f.write(json_response)

async def parse_variants_task_async(paper: Paper, gene_symbol: str) -> None:
    result = await Runner.run(
        variant_extraction_agent,
        f"Gene Symbol: {gene_symbol}\nPaper (fulltext md): {paper.fulltext_md}",
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper.variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper.variants_json_path, "w") as f:
        f.write(json_response)

async def run_tasks_concurrently(paper: Paper, gene_symbol: str) -> None:
    await asyncio.gather(
        parse_patients_task_async(paper),
        parse_variants_task_async(paper, gene_symbol),
    )


def initial_extraction(paper_db: PaperDB) -> None:
    max_attempts = RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            paper = Paper(id=paper_db.id).with_content()
            parse_content(paper, force=True)
            paper = parse_paper_metadata_task(paper)
            asyncio.run(run_tasks_concurrently(paper, paper_db.gene.symbol))
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
