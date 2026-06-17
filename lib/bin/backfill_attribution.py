#!/usr/bin/env python3
"""Attribute all existing un-attributed rows to a user (one-off seed).

Pre-migration papers and entities have ``updated_by_user_id = NULL`` because the
user system did not exist when they were created. This backfills that audit
column to a single user so legacy data is attributed.

Only rows where ``updated_by_user_id IS NULL`` are touched, so this is safe to
re-run and will never clobber a genuine editor recorded by a later manual edit.
``updated_at`` is intentionally left untouched: this is historical attribution,
not a fresh edit.

Usage:
    uv run python -m lib.bin.backfill_attribution <email>
"""

import sys

from lib.api.db import session_scope
from lib.models import (
    FamilyDB,
    HarmonizedVariantDB,
    PaperDB,
    PatientDB,
    PhenotypeDB,
    SegregationEvidenceDB,
    UserDB,
    VariantDB,
)
from lib.tasks.models import TaskDB

# Mirror the audited tables from migration a1b2c3d4e5f6 plus tasks (b2c3d4e5f6a7).
# enriched/annotated variants are intentionally excluded -- they have no
# updated_by_user_id column.
_ATTRIBUTED_MODELS = (
    PaperDB,
    PatientDB,
    FamilyDB,
    VariantDB,
    HarmonizedVariantDB,
    PhenotypeDB,
    SegregationEvidenceDB,
    TaskDB,
)


def backfill(email: str) -> None:
    with session_scope() as session:
        user = session.query(UserDB).filter_by(email=email).one_or_none()
        if user is None:
            print(f'Error: no user found with email {email}', file=sys.stderr)
            sys.exit(1)

        for model in _ATTRIBUTED_MODELS:
            column = getattr(model, 'updated_by_user_id')
            updated = (
                session.query(model)
                .filter(column.is_(None))
                .update(
                    {column: user.id},
                    synchronize_session=False,
                )
            )
            print(f'{model.__tablename__}: attributed {updated} rows to {email}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} <email>', file=sys.stderr)
        sys.exit(1)
    backfill(sys.argv[1])
