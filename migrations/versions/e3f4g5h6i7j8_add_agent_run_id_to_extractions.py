"""Add agent_run_id to extraction tables

Revision ID: e3f4g5h6i7j8
Revises: c1d2e3f4g5h6
Create Date: 2026-05-21 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = 'e3f4g5h6i7j8'
down_revision: Union[str, None] = 'c1d2e3f4g5h6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from lib.agents.run_tracking import ensure_agent_run

    # Create the initial agent run using ensure_agent_run
    session = Session(bind=op.get_bind())
    run = ensure_agent_run(session, description='Initial baseline run')
    session.commit()
    run_id = run.id

    conn = op.get_bind()

    # Add agent_run_id columns and backfill with run_id using batch mode for each table
    for table_name in ['patients', 'variants']:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'agent_run_id',
                    sa.Integer(),
                    nullable=False,
                    server_default=str(run_id),
                )
            )
            batch_op.create_foreign_key(
                f'fk_{table_name}_agent_run_id',
                'agent_runs',
                ['agent_run_id'],
                ['id'],
                ondelete='CASCADE',
            )
            batch_op.create_index(f'ix_{table_name}_agent_run_id', ['agent_run_id'])


def downgrade() -> None:
    for table_name in ['variants', 'patients']:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f'ix_{table_name}_agent_run_id')
            batch_op.drop_constraint(
                f'fk_{table_name}_agent_run_id', type_='foreignkey'
            )
            batch_op.drop_column('agent_run_id')
