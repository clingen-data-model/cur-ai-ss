"""upsert gene symbols

Revision ID: eb6bb798b30f
Revises: a67ad1f5c9b7
Create Date: 2026-03-05 16:04:39.887523

"""

import traceback
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from lib.core.environment import env

# revision identifiers, used by Alembic.
revision: str = 'eb6bb798b30f'
down_revision: Union[str, None] = '1b59c56b7902'
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
