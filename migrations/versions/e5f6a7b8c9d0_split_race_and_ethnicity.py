"""split patients.race_ethnicity into separate race and ethnicity fields

Race/ethnicity were previously a single combined field using gnomAD-style
ancestry categories (East Asian, Ashkenazi Jewish, Finnish, etc). This splits
it into independent `race` and `ethnicity` fields using OMB-style categories.

The old categories don't map cleanly onto the new taxonomy, so only the
unambiguous cases are backfilled (e.g. East Asian -> Race=Asian); everything
else (Ashkenazi Jewish, Finnish, Middle Eastern, Amish, Other, Unknown) falls
back to Unknown/Unknown pending re-extraction. The old evidence blob is copied
to both new evidence columns since there's no way to split it retroactively.

`patients` has CASCADE dependents (phenotypes, patient_variant_occurrences),
so foreign keys are disabled around the batch alters per project convention.

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-07
"""

import sqlalchemy as sa
from alembic import op

revision = 'e5f6a7b8c9d0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

_RACE_BY_OLD_VALUE = {
    'African/African American': 'Black',
    'East Asian': 'Asian',
    'South Asian': 'Asian',
    'Non-Finnish European': 'White',
}

_ETHNICITY_BY_OLD_VALUE = {
    'Latino/Admixed American': 'Hispanic or Latino',
    'Non-Finnish European': 'Not Hispanic or Latino',
}


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        with op.batch_alter_table('patients', schema=None) as batch_op:
            batch_op.add_column(sa.Column('race', sa.String(), nullable=True))
            batch_op.add_column(sa.Column('ethnicity', sa.String(), nullable=True))
            batch_op.add_column(sa.Column('race_evidence', sa.JSON(), nullable=True))
            batch_op.add_column(
                sa.Column('ethnicity_evidence', sa.JSON(), nullable=True)
            )

        connection.execute(sa.text("UPDATE patients SET race = 'Unknown'"))
        connection.execute(sa.text("UPDATE patients SET ethnicity = 'Unknown'"))
        for old_value, race_value in _RACE_BY_OLD_VALUE.items():
            connection.execute(
                sa.text(
                    'UPDATE patients SET race = :race_value '
                    'WHERE race_ethnicity = :old_value'
                ),
                {'race_value': race_value, 'old_value': old_value},
            )
        for old_value, ethnicity_value in _ETHNICITY_BY_OLD_VALUE.items():
            connection.execute(
                sa.text(
                    'UPDATE patients SET ethnicity = :ethnicity_value '
                    'WHERE race_ethnicity = :old_value'
                ),
                {'ethnicity_value': ethnicity_value, 'old_value': old_value},
            )
        connection.execute(
            sa.text(
                'UPDATE patients SET race_evidence = race_ethnicity_evidence, '
                'ethnicity_evidence = race_ethnicity_evidence'
            )
        )

        with op.batch_alter_table('patients', schema=None) as batch_op:
            batch_op.alter_column('race', existing_type=sa.String(), nullable=False)
            batch_op.alter_column(
                'ethnicity', existing_type=sa.String(), nullable=False
            )
            batch_op.alter_column(
                'race_evidence', existing_type=sa.JSON(), nullable=False
            )
            batch_op.alter_column(
                'ethnicity_evidence', existing_type=sa.JSON(), nullable=False
            )
            batch_op.drop_column('race_ethnicity')
            batch_op.drop_column('race_ethnicity_evidence')
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))


def downgrade() -> None:
    pass
