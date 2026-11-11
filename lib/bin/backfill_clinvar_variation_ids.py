#!/usr/bin/env python3
"""Backfill the ClinVar variation ID on existing annotated variants (one-off).

``annotated_variants.clinvar_variation_id`` was added after variant annotation
had already run, so older rows have it NULL and the UI can only offer a ClinVar
search instead of the record. This repeats the annotation's ClinVar lookup
(the annotated row's rsID and CAID, the harmonized HGVS) and stores the ID it
lands on, but only when that record still gives the classification stored on
the row: ClinVar's ranking or classifications may have moved since, and a link
to a record that disagrees with the value shown beside it is worse than a
search. Those rows are reported and left for a Variant Annotation re-run.

Only rows with a stored classification and no ID are touched, so this is safe to
re-run. ``updated_at`` is left alone: this is a backfill, not a re-annotation.

Usage:
    uv run python -m lib.bin.backfill_clinvar_variation_ids [--dry-run]
"""

import argparse
import sys
import time

from lib.agents.variant_annotation_agent import clinvar_lookup
from lib.api.db import session_scope
from lib.core.environment import env
from lib.models import AnnotatedVariantDB


def request_interval_seconds() -> float:
    # Two E-utilities requests per lookup; NCBI allows 3 requests a second
    # without an API key and 10 with one.
    return 0.25 if env.NCBI_API_KEY else 0.75


def backfill(dry_run: bool = False) -> None:
    with session_scope() as session:
        rows = (
            session.query(AnnotatedVariantDB)
            .filter(
                AnnotatedVariantDB.clinvar_variation_id.is_(None),
                AnnotatedVariantDB.pathogenicity.isnot(None),
                AnnotatedVariantDB.pathogenicity != '',
            )
            .order_by(AnnotatedVariantDB.id)
            .all()
        )
        if not rows:
            print('Nothing to backfill.')
            return

        print(f'Looking up ClinVar variation IDs for {len(rows)} annotated variants.')

        updated = 0
        mismatched = 0
        for index, row in enumerate(rows):
            if index:
                time.sleep(request_interval_seconds())

            harmonized = row.variant.harmonized_variant
            result = clinvar_lookup(
                row.rsid,
                row.caid,
                harmonized.hgvs_g if harmonized else None,
                harmonized.hgvs_c if harmonized else None,
            )
            label = f'variant {row.variant_id} ({row.rsid or row.caid or "no id"})'

            if result.clinvar_variation_id is None:
                print(f'  {label}: no ClinVar record found')
                continue
            if result.pathogenicity != row.pathogenicity:
                mismatched += 1
                print(
                    f'  {label}: record {result.clinvar_variation_id} now says '
                    f'{result.pathogenicity!r}, stored {row.pathogenicity!r}; skipped'
                )
                continue

            print(f'  {label}: {result.clinvar_variation_id}')
            if not dry_run:
                row.clinvar_variation_id = result.clinvar_variation_id
            updated += 1

        if dry_run:
            session.rollback()
            print(f'Dry run: {updated} would be filled, {mismatched} disagree.')
        else:
            print(f'Filled {updated}; {mismatched} disagree and need a re-annotation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Query ClinVar and report what would change without writing.',
    )
    args = parser.parse_args()
    try:
        backfill(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print('Interrupted.', file=sys.stderr)
        sys.exit(1)
