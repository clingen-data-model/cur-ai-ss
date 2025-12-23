import datetime
import json
import logging
import time
import traceback

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.db import session_scope
from app.models import ExtractionStatus, PaperDB
from lib.evagg import App
from lib.evagg.types.base import Paper
from lib.evagg.utils import init_logger

POLL_INTERVAL_S = 10
RETRIES = 3

logger = logging.getLogger(__name__)


def run_evagg_app(paper_id) -> None:
    init_logger(
        current_run=f'{paper_id}_{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}'
    )
    max_attempts = RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            paper = Paper(id=paper_id).with_content()
            res = App(paper).execute()
            if not res:
                return
            with open(paper.evagg_observations_path, 'w') as f:
                json.dump(res, f)
            mark_paper_as_extraction_status(paper_id, ExtractionStatus.EXTRACTED)
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


def mark_paper_as_extraction_status(paper_id: str, extraction_status: ExtractionStatus):
    if paper_id:
        with session_scope() as session:
            session.execute(
                update(PaperDB)
                .where(PaperDB.id == paper_id)
                .values(extraction_status=extraction_status)
            )
            session.commit()


def main():
    while True:
        paper_id = None
        try:
            with session_scope() as session:
                paper_id = session.scalars(
                    select(PaperDB.id)
                    .where(PaperDB.extraction_status == ExtractionStatus.QUEUED)
                    .order_by(PaperDB.id)
                    .limit(1)
                ).first()
            if paper_id:
                print(f'Dequeued paper {paper_id}')
                run_evagg_app(paper_id)
        except KeyboardInterrupt:
            print('Shutting down poller')
            break
        except SQLAlchemyError as e:
            print(f'Database error occurred: {e}')
            mark_paper_as_extraction_status(paper_id, ExtractionStatus.FAILED)
        except Exception as e:
            print(f'An unexpected error occurred: {e}')
            mark_paper_as_extraction_status(paper_id, ExtractionStatus.FAILED)
        time.sleep(POLL_INTERVAL_S)
        print('waiting for work')


if __name__ == '__main__':
    main()
