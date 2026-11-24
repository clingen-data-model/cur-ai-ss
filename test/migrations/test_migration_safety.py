"""Generic safety checks that every migration gets without a test of its own.

Two failures have destroyed production data here, and both are silent while the
migration runs (CLAUDE.md, "Migrations (SQLite)"):

- ``batch_alter_table`` recreating a parent table with foreign keys still on
  deletes every CASCADE child row.
- Escaping alembic's transaction with ``connection.commit()`` leaves
  ``alembic_version`` one revision behind, so the next ``upgrade head`` runs the
  destructive DDL again.

And one has broken reads: an Enum column written with the member's value instead
of its name, which only fails when the ORM loads the row (``LookupError``).

``test_every_migration_keeps_every_row`` upgrades to ``BASELINE`` and from there
walks the chain one revision at a time. Before each step it gives every empty
table one row whose foreign keys point at the parent tables' rows, so each CASCADE
relationship has a child to lose; after it, it asserts that no table lost rows and
that ``alembic_version`` landed on the step. At head it checks the Enum columns
hold member names, loads every model through the ORM, and runs ``upgrade head``
once more to show it changes nothing.

The walk starts at ``BASELINE`` because the migrations before it ran on
production long ago and only ever run again on an empty database, and some of
them could not take one another's data anyway (``3b2d941d02a2`` backfills an
evidence column with ``[]``, which ``24aa340de723`` cannot read).
``test_the_walk_catches_the_june_cascade`` replays the June 2026 incident to
show the walk still sees a cascade.

The seeded values are generic (zeros, ``'x'``, empty JSON). A migration whose
data step needs realistic rows still wants a test of its own in
``test_alembic.py``.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, Connection, Enum, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lib.api import db
from lib.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]

# The walk starts after this revision (see the module docstring). Leave it be:
# every migration added later is walked.
BASELINE = '24aa340de723'

# Revisions that delete rows on purpose, and from which tables. A migration that
# drops a table needs no entry: a table that no longer exists is not counted.
EXPECTED_ROW_LOSS: dict[str, set[str]] = {}


@pytest.fixture
def alembic_cfg(monkeypatch, tmp_path) -> Config:
    monkeypatch.setattr(db.env, 'CAA_ROOT', str(tmp_path))
    monkeypatch.setattr(db.env, 'SQLLITE_DIR', '')
    monkeypatch.setattr(db, '_engine', None)
    monkeypatch.setattr(db, '_session_factory', None)
    return Config(str(REPO_ROOT / 'alembic.ini'))


def _revisions_base_to_head(cfg: Config) -> list[str]:
    script = ScriptDirectory.from_config(cfg)
    return [r.revision for r in reversed(list(script.walk_revisions()))]


def _head_column(table: str, column: str) -> Any:
    head_table = Base.metadata.tables.get(table)
    if head_table is None or column not in head_table.columns:
        return None
    return head_table.columns[column]


def _seed_value(table: str, column: dict[str, Any]) -> Any:
    """A value the column accepts, preferring what the head model says it is."""
    name = column['name']
    head = _head_column(table, name)
    if head is not None and isinstance(head.type, Enum):
        return head.type.enums[0]
    type_name = str(column['type']).upper()
    if (head is not None and isinstance(head.type, JSON)) or 'JSON' in type_name:
        # Evidence blocks are objects; the other JSON columns are mostly lists.
        if name.endswith('evidence'):
            return json.dumps({'value': None, 'reasoning': 'x'})
        return json.dumps([])
    if 'BOOL' in type_name:
        return False
    if 'INT' in type_name:
        return 0
    if any(t in type_name for t in ('FLOAT', 'REAL', 'NUMERIC', 'DOUBLE')):
        return 0.0
    if 'DATE' in type_name or 'TIME' in type_name:
        return '2026-01-01 00:00:00.000000'
    return 'x'


def _row_counts(connection: Connection) -> dict[str, int]:
    tables = [
        t for t in inspect(connection).get_table_names() if t != 'alembic_version'
    ]
    return {
        t: connection.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one()
        for t in tables
    }


def _seed_empty_tables(connection: Connection) -> None:
    """Insert one row into every empty table, parents before children.

    A foreign key points at the referenced table's first row. A table with a
    required key into a table that is still empty waits for a later round, or for
    the next migration.
    """
    inspector = inspect(connection)
    tables = [t for t in inspector.get_table_names() if t != 'alembic_version']
    counts = _row_counts(connection)
    pending = [t for t in tables if not counts.get(t)]
    while pending:
        progressed = False
        for table in list(pending):
            if _insert_seed_row(connection, table):
                pending.remove(table)
                progressed = True
        if not progressed:
            return


def _insert_seed_row(connection: Connection, table: str) -> bool:
    """Insert a row, trying the foreign-key fillings in ``_seed_rows`` in turn.

    Each try runs in a savepoint, so a CHECK the filling breaks (``edits`` points
    at exactly one entity) only moves on to the next.
    """
    for row in _seed_rows(connection, table):
        columns = ', '.join(f'"{c}"' for c in row)
        params = ', '.join(f':p{i}' for i in range(len(row)))
        savepoint = connection.begin_nested()
        try:
            connection.execute(
                text(f'INSERT INTO "{table}" ({columns}) VALUES ({params})'),
                {f'p{i}': v for i, v in enumerate(row.values())},
            )
        except IntegrityError:
            savepoint.rollback()
            continue
        savepoint.commit()
        return True
    return False


def _seed_rows(connection: Connection, table: str) -> list[dict[str, Any]]:
    """Candidate rows: every foreign key filled (the most CASCADE children),
    then the nullable ones left NULL, then each nullable one filled alone.
    No candidates while a required key's parent table is empty."""
    inspector = inspect(connection)
    foreign: dict[str, tuple[str, str]] = {}
    for fk in inspector.get_foreign_keys(table):
        for local, remote in zip(fk['constrained_columns'], fk['referred_columns']):
            foreign[local] = (fk['referred_table'], remote)
    primary_key = set(inspector.get_pk_constraint(table)['constrained_columns'])

    base: dict[str, Any] = {}
    optional: dict[str, Any] = {}
    for column in inspector.get_columns(table):
        name = column['name']
        if name in foreign:
            parent, remote = foreign[name]
            value = connection.execute(
                text(f'SELECT "{remote}" FROM "{parent}" LIMIT 1')
            ).scalar()
            if column['nullable']:
                if value is not None:
                    optional[name] = value
            elif value is None:
                return []
            else:
                base[name] = value
        elif name in primary_key and 'INT' in str(column['type']).upper():
            continue  # autoincrement
        elif column['nullable'] or column.get('default') is not None:
            continue
        else:
            base[name] = _seed_value(table, column)

    candidates = [{**base, **optional}, base]
    candidates += [{**base, name: value} for name, value in optional.items()]
    return candidates


def _alembic_version(connection: Connection) -> list[str]:
    return [
        r[0]
        for r in connection.execute(text('SELECT version_num FROM alembic_version'))
    ]


def test_single_head(alembic_cfg):
    heads = ScriptDirectory.from_config(alembic_cfg).get_heads()
    assert len(heads) == 1, (
        f'migrations have {len(heads)} heads {heads}; merge them '
        '(`uv run alembic merge heads`) or rebase the newer one onto the other'
    )


def _walk(cfg: Config, start: str, stop: str) -> dict[str, dict[str, tuple[int, int]]]:
    """Upgrade to ``start``, then one revision at a time to ``stop``, seeding
    empty tables before each step. Returns the rows each step lost, by table
    (before, after), leaving out ``EXPECTED_ROW_LOSS``."""
    engine = db.get_engine()
    revisions = _revisions_base_to_head(cfg)
    command.upgrade(cfg, start)
    losses = {}
    for revision in revisions[revisions.index(start) + 1 : revisions.index(stop) + 1]:
        with engine.begin() as connection:
            _seed_empty_tables(connection)
            before = _row_counts(connection)

        command.upgrade(cfg, revision)

        with engine.connect() as connection:
            version = _alembic_version(connection)
            assert version == [revision], (
                f'{revision} ran but alembic_version is {version}; did it commit '
                "alembic's transaction? Use autocommit_block() instead"
            )
            after = _row_counts(connection)
        lost = {
            table: (count, after[table])
            for table, count in before.items()
            if table in after
            and after[table] < count
            and table not in EXPECTED_ROW_LOSS.get(revision, set())
        }
        if lost:
            losses[revision] = lost
    return losses


def test_the_walk_catches_the_june_cascade(alembic_cfg):
    """3b2d941d02a2 batch-altered families with foreign keys on and deleted every
    patient on production (June 2026). If the walk stopped seeing that, the seeder
    broke and the test below would pass on anything."""
    losses = _walk(alembic_cfg, '3ba072e85738', '3b2d941d02a2')
    assert 'patients' in losses.get('3b2d941d02a2', {})


def test_every_migration_keeps_every_row(alembic_cfg):
    engine = db.get_engine()
    revisions = _revisions_base_to_head(alembic_cfg)

    losses = _walk(alembic_cfg, BASELINE, revisions[-1])
    assert not losses, (
        f'migrations deleted rows (revision: table: (before, after)): {losses}. '
        'A batch_alter_table on a parent with CASCADE children deletes them '
        'unless foreign keys are off; see CLAUDE.md, "Migrations (SQLite)"'
    )

    with engine.begin() as connection:
        _seed_empty_tables(connection)
        counts = _row_counts(connection)
    assert all(counts.values()), (
        f'tables the seeder could not fill: {[t for t, n in counts.items() if not n]}'
    )

    # Enum columns store the member's name; a value fails only on read.
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if not isinstance(column.type, Enum):
                    continue
                # Raw SQL, so the stored string comes back, not a converted member.
                stored = {
                    v
                    for (v,) in connection.execute(
                        text(
                            f'SELECT DISTINCT "{column.name}" FROM "{table.name}" '
                            f'WHERE "{column.name}" IS NOT NULL'
                        )
                    )
                }
                unknown = stored - set(column.type.enums)
                assert not unknown, (
                    f'{table.name}.{column.name} holds {unknown}, which are not '
                    f'member names {column.type.enums}; a server_default or '
                    "backfill must write the member's .name"
                )

    with Session(engine) as session:
        for mapper in Base.registry.mappers:
            session.execute(select(mapper.class_)).scalars().all()

    command.upgrade(alembic_cfg, 'head')
    with engine.connect() as connection:
        assert _alembic_version(connection) == [revisions[-1]]
        assert _row_counts(connection) == counts
