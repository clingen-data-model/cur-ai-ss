"""rename paper acknowledgement to paper classifier

Revision ID: a7c8d9e0f1g2
Revises: 6c4eb1b68b03
Create Date: 2026-05-21 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c8d9e0f1g2'
down_revision: Union[str, None] = '6c4eb1b68b03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate existing 'Paper Acknowledgement' tasks to 'Paper Classifier'."""
    # Update existing records
    op.execute(
        "UPDATE tasks SET type = 'Paper Classifier' WHERE type = 'Paper Acknowledgement'"
    )


def downgrade() -> None:
    """Revert to 'Paper Acknowledgement' task type."""
    op.execute(
        "UPDATE tasks SET type = 'Paper Acknowledgement' WHERE type = 'Paper Classifier'"
    )
