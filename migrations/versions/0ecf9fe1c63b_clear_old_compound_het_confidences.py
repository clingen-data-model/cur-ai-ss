"""clear_old_compound_het_confidences

Revision ID: 0ecf9fe1c63b
Revises: 3b2d941d02a2
Create Date: 2026-06-04 13:11:10.288943

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0ecf9fe1c63b'
down_revision: Union[str, None] = '3b2d941d02a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear old compound het confidence data (high/medium/low) to allow re-running agent with new values (confirmed/assumed/uncertain)
    op.execute(
        'UPDATE patient_variant_occurrences SET paired_variant_confidence = NULL, paired_variant_confidence_reasoning = NULL WHERE paired_variant_confidence IS NOT NULL'
    )


def downgrade() -> None:
    # Cannot restore old confidence values, so downgrade is a no-op
    pass
