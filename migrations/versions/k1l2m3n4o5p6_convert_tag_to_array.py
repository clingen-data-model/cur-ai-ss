"""convert tag enum to tag array

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-05-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # Migrate data from old enum tag column to tags JSON column
    result = connection.execute(
        sa.text('SELECT id, tag FROM papers WHERE tag IS NOT NULL')
    )
    for row in result:
        paper_id = row[0]
        tag_value = row[1]
        # Convert enum value to JSON array
        connection.execute(
            sa.text('UPDATE papers SET tags = json(:tags) WHERE id = :id'),
            {'tags': f'["{tag_value}"]', 'id': paper_id},
        )
    connection.commit()

    # Drop the old enum tag column and rename tags to tag
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('tag')
        batch_op.alter_column('tags', new_column_name='tag')


def downgrade() -> None:
    connection = op.get_bind()

    # Rename tag back to tags and recreate the old enum column
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.alter_column('tag', new_column_name='tags')
        batch_op.add_column(
            sa.Column('tag', sa.Enum('TrainingSet', 'ValidationSet'), nullable=True)
        )

    # Migrate data back from tags to tag (take first element if it exists)
    result = connection.execute(
        sa.text('SELECT id, tags FROM papers WHERE tags != "[]"')
    )
    for row in result:
        paper_id = row[0]
        tags_json = row[1]
        # Extract first tag from JSON array
        connection.execute(
            sa.text(
                'UPDATE papers SET tag = json_extract(:tags, "$[0]") WHERE id = :id'
            ),
            {'tags': tags_json, 'id': paper_id},
        )
    connection.commit()
