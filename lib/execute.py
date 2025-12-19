import argparse
import datetime
import logging
import traceback

from lib.evagg import App
from lib.evagg.utils import init_logger

from pathlib import Path


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Process a PMID and gene symbol.')
    parser.add_argument('--pdf', help='PDF', required=True, type=Path)
    parser.add_argument('--gene-symbol', help='Gene symbol', required=True, type=str)
    parser.add_argument(
        '--retries',
        type=int,
        default=0,
        help='Number of times to retry on error (default: 0)',
    )
    return parser.parse_args()


def run_evagg_app() -> None:
    args = parse_args()
    init_logger(
        current_run=f'{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}'
    )
    if not args.pdf.exists():
        raise RuntimeError('pdf path must exist')
    with open(args.pdf, 'rb') as f:
        content = f.read()
    app = App(
        content,
        args.gene_symbol,
    )
    max_attempts = args.retries + 1
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f'Attempt {attempt}/{max_attempts}')
            app.execute()
            return
        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
        except Exception as e:
            logger.error(f'Error executing app on attempt {attempt}: {e}')
            logger.error(traceback.format_exc())
            if attempt == max_attempts:
                logger.error('All retries exhausted. Exiting.')
                raise


if __name__ == '__main__':
    run_evagg_app()
