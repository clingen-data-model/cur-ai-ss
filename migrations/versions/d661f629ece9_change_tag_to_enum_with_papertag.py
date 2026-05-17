"""change tag to enum with PaperTag

Revision ID: d661f629ece9
Revises: f1a2b3c4d5e6
Create Date: 2026-05-16 00:53:04.330085

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd661f629ece9'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'papers',
        sa.Column(
            'tag',
            sa.Enum('TrainingSet', 'ValidationSet', name='papertag'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('papers', 'tag')
