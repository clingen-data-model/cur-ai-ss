"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

# The deploy (bin/migrate) and CI (test_migration_safety) fail when a table that
# exists before and after this migration has fewer rows afterwards. Declare what
# this migration does to rows on purpose; a dropped table needs nothing.
# deletes_rows_from = {'table'}       # this table may lose rows
# renames = {'old_name': 'new_name'}  # compare old_name's count to new_name's


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
