#!/usr/bin/env python3

import csv
import io
from typing import Iterable

import requests
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from lib.api.db import get_sessionmaker
from lib.models import GeneDB

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
    print('Downloading HGNC gene set...')
    symbols = download_hgnc_symbols()
    print(f'Downloaded {len(symbols)} symbols.')

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        sync_genes_via_temp_table(session, symbols)


if __name__ == '__main__':
    main()
