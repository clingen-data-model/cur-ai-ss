"""pedigrees becomes figure_descriptions: one row per described figure

The Figure Description step is growing from "the paper's one pedigree" to
every figure extraction can read (pedigrees, chromatograms, gels,
copy-number plots, read pileups, karyotypes). ``pedigrees`` held at most one
row per paper (UNIQUE paper_id); ``figure_descriptions`` holds one row per
figure, each with a ``kinds`` JSON list of readable FigureKind values, unique
per (paper, section, image). Every existing row is a pedigree by definition,
so it is copied across with kinds ["Pedigree"], keeping its id, and the old
table is dropped.

No batch alteration and no CASCADE dependents: ``pedigrees`` is a leaf
table, so CREATE, INSERT ... SELECT and DROP are plain statements (see the
migration-safety section of CLAUDE.md). The row count is checked before the
drop. Snapshot files still carry a ``pedigrees`` key; lib.misc.snapshots maps
it on restore, so they are left alone.

Revision ID: c4d8e1f2a9b7
Revises: a3f9c2e7d1b4
Create Date: 2026-10-21 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'c4d8e1f2a9b7'
down_revision: Union[str, None] = 'a3f9c2e7d1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _count(table: str) -> int:
    return op.get_bind().execute(text(f'SELECT count(*) FROM {table}')).scalar_one()


def upgrade() -> None:
    op.create_table(
        'figure_descriptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('image_id', sa.Integer(), nullable=False),
        sa.Column('is_supplement', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('kinds', sa.JSON(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paper_id', 'is_supplement', 'image_id'),
    )
    op.create_index(
        'ix_figure_descriptions_paper_id', 'figure_descriptions', ['paper_id']
    )

    before = _count('pedigrees')
    op.execute(
        'INSERT INTO figure_descriptions '
        '(id, paper_id, image_id, is_supplement, kinds, description, updated_at) '
        'SELECT id, paper_id, image_id, is_supplement, \'["Pedigree"]\', '
        'description, updated_at FROM pedigrees'
    )
    after = _count('figure_descriptions')
    if after != before:
        raise RuntimeError(
            f'figure_descriptions has {after} rows but pedigrees had {before}; '
            'refusing to drop pedigrees'
        )

    op.drop_index('ix_pedigrees_paper_id', table_name='pedigrees')
    op.drop_table('pedigrees')


def downgrade() -> None:
    op.create_table(
        'pedigrees',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('image_id', sa.Integer(), nullable=False),
        sa.Column('is_supplement', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paper_id'),
        sa.UniqueConstraint('paper_id', 'image_id'),
    )
    op.create_index('ix_pedigrees_paper_id', 'pedigrees', ['paper_id'])

    # The old table holds one pedigree per paper: the first described one.
    op.execute(
        'INSERT INTO pedigrees '
        '(id, paper_id, image_id, is_supplement, description, updated_at) '
        'SELECT id, paper_id, image_id, is_supplement, description, updated_at '
        'FROM figure_descriptions f '
        'WHERE kinds LIKE \'%"Pedigree"%\' AND id = ('
        '  SELECT min(id) FROM figure_descriptions g '
        '  WHERE g.paper_id = f.paper_id AND g.kinds LIKE \'%"Pedigree"%\')'
    )

    op.drop_index('ix_figure_descriptions_paper_id', table_name='figure_descriptions')
    op.drop_table('figure_descriptions')
