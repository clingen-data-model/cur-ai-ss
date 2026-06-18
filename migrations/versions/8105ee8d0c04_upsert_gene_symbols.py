"""upsert gene symbols

Revision ID: 8105ee8d0c04
Revises: 0001_squashed_initial_schema
Create Date: 2026-05-27 00:40:00.000000

"""

import traceback
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from lib.core.environment import env

# revision identifiers, used by Alembic.
revision: str = '8105ee8d0c04'
down_revision: Union[str, None] = '0001_squashed_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if env.SKIP_DATA_MIGRATIONS:
        return
    try:
        from lib.reference_data.upsert_gene_symbols import main

        main()
    except Exception as e:
        # Print full traceback for debugging
        print('Error running upsert_gene_symbols migration:')
        traceback.print_exc()
        # Optionally, re-raise to fail the migration
        raise


def downgrade() -> None:
    pass
