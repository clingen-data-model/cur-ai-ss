#!/usr/bin/env python3

import csv
import io
from typing import Iterable

import requests
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from lib.api.db import get_sessionmaker
from lib.models import GeneDB
from lib.reference_data.file_headers import should_update_file, update_cached_headers

HGNC_URL = 'https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt'


def download_hgnc_symbols() -> list[str]:
    """Download HGNC TSV and return a list of gene symbols."""
    resp = requests.get(HGNC_URL, timeout=60)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text), delimiter='\t')

    # HGNC uses 'symbol' as the approved gene symbol column
    symbols = []
    for row in reader:
        symbol = row.get('symbol')
        if symbol:
            symbols.append(symbol)

    return symbols


def sync_genes_via_temp_table(session: Session, symbols: list[str]) -> None:
    # 1. temp table
    session.execute(
        text("""
        CREATE TEMPORARY TABLE tmp_hgnc_genes (
            symbol TEXT PRIMARY KEY
        )
    """)
    )

    # 2. bulk insert into temp table (executemany, no IN clause)
    session.execute(
        text('INSERT INTO tmp_hgnc_genes (symbol) VALUES (:symbol)'),
        [{'symbol': s} for s in symbols],
    )

    # 3. insert missing genes
    session.execute(
        text("""
        INSERT INTO genes (symbol)
        SELECT t.symbol
        FROM tmp_hgnc_genes t
        LEFT JOIN genes g ON g.symbol = t.symbol
        WHERE g.symbol IS NULL
    """)
    )

    # 4. delete genes not in HGNC
    session.execute(
        text("""
        DELETE FROM genes
        WHERE NOT EXISTS (
            SELECT 1
            FROM tmp_hgnc_genes t
            WHERE t.symbol = genes.symbol
        )
    """)
    )

    session.commit()


def main() -> None:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        if not should_update_file(
            session, 'hgnc_complete_set', HGNC_URL, model_class=GeneDB
        ):
            print('HGNC gene set is up to date, skipping download.')
            return

        print('Downloading HGNC gene set...')
        symbols = download_hgnc_symbols()
        print(f'Downloaded {len(symbols)} symbols.')

        sync_genes_via_temp_table(session, symbols)

        update_cached_headers(session, 'hgnc_complete_set', HGNC_URL)


if __name__ == '__main__':
    main()
