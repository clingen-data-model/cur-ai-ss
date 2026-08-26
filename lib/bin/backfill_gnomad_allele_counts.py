#!/usr/bin/env python3
"""Backfill gnomAD allele counts on existing annotated variants (one-off).

``gnomad_ac``, ``gnomad_an``, ``gnomad_popmax_ac`` and ``gnomad_popmax_an`` were
added after variant annotation had already run, so rows written before the
migration have them as NULL. This re-queries gnomAD for each annotated variant
that has gnomAD-style coordinates and updates those four columns. Allele
frequencies are filled in only where they are currently NULL, so stored values
are never clobbered; ClinVar and VEP columns are left untouched entirely.

Only rows missing the counts are touched by default, so this is safe to re-run.
``updated_at`` is intentionally left untouched: this is a historical backfill,
not a fresh annotation.

gnomAD is queried at most once per second to stay friendly to their public API.

Usage:
    uv run python -m lib.bin.backfill_gnomad_allele_counts [--all] [--dry-run]
"""

import argparse
import sys
import time

from lib.agents.variant_annotation_agent import gnomad_lookup
from lib.api.db import session_scope
from lib.models import AnnotatedVariantDB

# gnomAD's public API is unmetered but shared; keep to one request per second.
REQUEST_INTERVAL_SECONDS = 1.0


def backfill(refresh_all: bool = False, dry_run: bool = False) -> None:
    with session_scope() as session:
        query = session.query(AnnotatedVariantDB).filter(
            AnnotatedVariantDB.gnomad_style_coordinates.isnot(None)
        )
        if not refresh_all:
            query = query.filter(AnnotatedVariantDB.gnomad_ac.is_(None))

        rows = query.order_by(AnnotatedVariantDB.id).all()
        if not rows:
            print('Nothing to backfill.')
            return

        print(f'Backfilling gnomAD allele counts for {len(rows)} annotated variants.')

        updated = 0
        for index, row in enumerate(rows):
            if index:
                time.sleep(REQUEST_INTERVAL_SECONDS)

            coordinates = row.gnomad_style_coordinates
            assert coordinates is not None  # guaranteed by the query filter
            result = gnomad_lookup(coordinates)

            if result.gnomad_an is None:
                print(f'  variant {row.variant_id} ({coordinates}): no gnomAD data')
                continue

            print(
                f'  variant {row.variant_id} ({coordinates}): '
                f'AC/AN {result.gnomad_ac}/{result.gnomad_an}, '
                f'popmax {result.gnomad_popmax_population or "N/A"} '
                f'{result.gnomad_popmax_ac}/{result.gnomad_popmax_an}'
            )

            if dry_run:
                continue

            row.gnomad_ac = result.gnomad_ac
            row.gnomad_an = result.gnomad_an
            row.gnomad_popmax_ac = result.gnomad_popmax_ac
            row.gnomad_popmax_an = result.gnomad_popmax_an

            # Frequencies were already stored by the annotation agent; only fill
            # them where they are missing, so a stored value is never clobbered
            # by a later gnomAD release.
            if row.gnomad_top_level_af is None:
                row.gnomad_top_level_af = result.gnomad_top_level_af
            if row.gnomad_popmax_af is None:
                row.gnomad_popmax_af = result.gnomad_popmax_af
            if row.gnomad_popmax_population is None:
                row.gnomad_popmax_population = result.gnomad_popmax_population

            updated += 1

        if dry_run:
            session.rollback()
            print(f'Dry run: {len(rows)} variants queried, nothing written.')
        else:
            print(f'Updated {updated} annotated variants.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--all',
        action='store_true',
        dest='refresh_all',
        help='Re-query every annotated variant, not just those missing counts.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Query gnomAD and report what would change without writing.',
    )
    args = parser.parse_args()
    try:
        backfill(refresh_all=args.refresh_all, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print('Interrupted.', file=sys.stderr)
        sys.exit(1)
