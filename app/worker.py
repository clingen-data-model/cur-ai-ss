import time

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.db import session_scope
from app.models import ExtractionStatus, PaperDB

POLL_INTERVAL_S = 10


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
            if not paper_id:
                continue
            print(paper_id)
            mark_paper_as_extraction_status(paper_id, ExtractionStatus.EXTRACTED)
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
