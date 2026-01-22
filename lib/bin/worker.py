#!/usr/bin/env python3
import asyncio
import datetime
import json
import logging
import time
import traceback

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

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


def dump_paper_metadata(paper: Paper) -> Paper:
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


def run_evagg_app(paper_db: PaperDB) -> None:
    max_attempts = RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            paper = Paper(id=paper_db.id).with_content()
            parse_content(paper)
            dump_paper_metadata(paper)
            paper_db.extraction_status = ExtractionStatus.PARSED
            logger.info(f'Attempt {attempt}/{max_attempts} succeeded')
            return
        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
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
                    run_evagg_app(paper_db)
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
            with session_scope() as session:
                paper_db = session.merge(paper_db)
                paper_db.extraction_status = ExtractionStatus.FAILED
        time.sleep(POLL_INTERVAL_S)
        logger.info('waiting for work')


if __name__ == '__main__':
    main()
