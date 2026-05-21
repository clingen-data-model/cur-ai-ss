"""add paper relevance and section classifications columns

Revision ID: b8d9e0f1g2h3
Revises: a7c8d9e0f1g2
Create Date: 2026-05-21 12:10:00.000000

"""

import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8d9e0f1g2h3'
down_revision: Union[str, None] = 'a7c8d9e0f1g2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_paper_relevant and section_classifications columns to papers table."""
    op.add_column('papers', sa.Column('is_paper_relevant', sa.Boolean(), nullable=True))
    op.add_column(
        'papers',
        sa.Column('section_classifications', sa.JSON(), nullable=True),
    )

    # Populate from existing JSON files on disk
    try:
        from lib.core.environment import env

        # Get a connection to execute raw SQL
        conn = op.get_bind()

        # Fetch all paper IDs
        result = conn.execute(sa.text('SELECT id FROM papers'))
        paper_ids = [row[0] for row in result]

        # For each paper, try to read its classification JSON and populate the DB
        for paper_id in paper_ids:
            classification_path = (
                env.extracted_pdf_dir
                / str(paper_id)
                / 'paper_section_classification.json'
            )
            if classification_path.exists():
                try:
                    data = json.loads(classification_path.read_text())
                    is_relevant = data.get('is_paper_relevant', True)
                    # Update the database with the loaded data
                    conn.execute(
                        sa.text(
                            'UPDATE papers SET is_paper_relevant = :is_relevant, '
                            'section_classifications = :classifications WHERE id = :paper_id'
                        ),
                        {
                            'is_relevant': is_relevant,
                            'classifications': json.dumps(data),
                            'paper_id': paper_id,
                        },
                    )
                except Exception:
                    # If reading fails, skip this paper
                    pass

        conn.commit()
    except Exception:
        # If we can't access the filesystem or environment, that's okay
        # The columns will just be empty for now
        pass


def downgrade() -> None:
    """Remove is_paper_relevant and section_classifications columns from papers table."""
    op.drop_column('papers', 'section_classifications')
    op.drop_column('papers', 'is_paper_relevant')
