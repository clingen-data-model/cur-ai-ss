"""Back up the database, migrate it to head, and check that no rows were lost.

The deployment runs this with the API and workers stopped, in place of the API's
old ``alembic upgrade head`` at startup (``MIGRATE_ON_STARTUP``, off on dev-caa).
Both ways migrations have destroyed production data were silent while they ran
(CLAUDE.md, "Migrations (SQLite)"), so this checks the two things that showed
them, and puts the database back if either is wrong:

- every table that exists before and after still has at least as many rows;
- ``alembic_version`` is head.

A database already at head is left alone. Otherwise it is snapshotted to
``<sqlite dir>/backups/app-premigrate-<UTC time>-<revision>.db`` with SQLite's
backup API first, and the newest ``--keep`` of those are kept.

A migration declares what it does to rows on purpose, beside its ``revision``,
and the check (here and in ``test/migrations/test_migration_safety.py``) follows
it; see ``declared_changes``:

    deletes_rows_from = {'flags'}               # these tables may lose rows
    renames = {'pedigrees': 'figure_descriptions'}  # compare old count to new name

``--allow-row-loss`` adds tables by hand, for someone running this on the VM.

``--backup-only`` takes a snapshot and nothing else, as
``app-daily-<UTC time>.db``; the nightly cron job runs it.

Exit status: 0 when the database is at head with nothing lost, 1 when a migration
failed or lost rows (the snapshot has been restored), 2 when the backup itself
failed (nothing was migrated).
"""

import argparse
import logging
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from lib.api import db
from lib.core.environment import env

logger = logging.getLogger('migrate')

REPO_ROOT = Path(__file__).resolve().parents[2]


def database_path() -> Path:
    return Path(env.sqlite_dir) / 'app.db'


def backup_dir() -> Path:
    return Path(env.sqlite_dir) / 'backups'


def alembic_config() -> Config:
    return Config(str(REPO_ROOT / 'alembic.ini'))


def head_revision(cfg: Config) -> str:
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f'expected one alembic head, found {heads}')
    return heads[0]


def current_revision(path: Path) -> str | None:
    """The revision in ``alembic_version``, None for a database alembic never ran on.
    Read directly rather than through alembic, which wants a SQLAlchemy engine."""
    with closing(sqlite3.connect(path)) as connection:
        has_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'alembic_version'"
        ).fetchone()
        if not has_table:
            return None
        versions = [
            v for (v,) in connection.execute('SELECT version_num FROM alembic_version')
        ]
    if len(versions) > 1:
        raise RuntimeError(f'alembic_version holds several revisions: {versions}')
    return versions[0] if versions else None


def row_counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(path)) as connection:
        tables = [
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            )
        ]
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }


def snapshot(path: Path, name: str) -> Path:
    """A consistent copy through SQLite's backup API, not a file copy that could
    catch a write half done."""
    backup_dir().mkdir(parents=True, exist_ok=True)
    destination = backup_dir() / name
    with (
        closing(sqlite3.connect(path)) as source,
        closing(sqlite3.connect(destination)) as target,
    ):
        source.backup(target)
    return destination


def prune(prefix: str, keep: int) -> None:
    snapshots = sorted(backup_dir().glob(f'{prefix}*.db'))
    for old in snapshots[:-keep] if keep > 0 else []:
        old.unlink()
        logger.info('Removed old snapshot %s', old.name)


def restore(backup: Path, path: Path) -> None:
    """Put the snapshot back. A journal left by the failed migration would be
    replayed onto the restored file, so it goes first."""
    db.get_engine().dispose()
    for suffix in ('-journal', '-wal', '-shm'):
        Path(f'{path}{suffix}').unlink(missing_ok=True)
    shutil.copy2(backup, path)


@dataclass
class DeclaredChanges:
    """What a run of migrations says it does to rows on purpose."""

    deletes_rows_from: set[str] = field(default_factory=set)
    renames: dict[str, str] = field(default_factory=dict)  # old name -> final name


def declared_changes(cfg: Config, start: str | None, stop: str) -> DeclaredChanges:
    """The ``deletes_rows_from`` and ``renames`` of the migrations after ``start``
    up to and including ``stop``. A table renamed twice maps to its last name."""
    script = ScriptDirectory.from_config(cfg)
    revisions = list(script.iterate_revisions(stop, start or 'base'))
    declared = DeclaredChanges()
    for revision in reversed(revisions):  # oldest first, so renames chain
        module = revision.module
        declared.deletes_rows_from |= set(getattr(module, 'deletes_rows_from', ()))
        for old, new in getattr(module, 'renames', {}).items():
            for first, latest in declared.renames.items():
                if latest == old:
                    declared.renames[first] = new
            declared.renames.setdefault(old, new)
    return declared


def lost_rows(
    before: dict[str, int], after: dict[str, int], declared: DeclaredChanges
) -> dict[str, tuple[int, int]]:
    """Tables with fewer rows after than before, by their name before. A renamed
    table is compared under its new name; a table gone afterwards, dropped, is
    not compared, and neither is one new afterwards."""
    lost = {}
    for table, count in before.items():
        name = declared.renames.get(table, table)
        if name not in after or after[name] >= count:
            continue
        if {table, name} & declared.deletes_rows_from:
            continue
        lost[table if name == table else f'{table} -> {name}'] = (count, after[name])
    return lost


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def migrate(allowed: set[str], keep: int) -> int:
    """``allowed``: tables given with ``--allow-row-loss``, on top of what the
    migrations declare."""
    cfg = alembic_config()
    head = head_revision(cfg)
    path = database_path()

    if not path.exists():
        logger.info('No database at %s; creating it at %s', path, head)
        command.upgrade(cfg, 'head')
        return 0

    current = current_revision(path)
    if current == head:
        logger.info('Database is at head (%s); nothing to migrate', head)
        return 0

    try:
        backup = snapshot(path, f'app-premigrate-{_timestamp()}-{current}.db')
    except Exception:
        logger.exception('Could not back up %s; not migrating', path)
        return 2
    logger.info('Backed up %s (at %s) to %s', path, current, backup)
    before = row_counts(path)
    declared = declared_changes(cfg, current, head)
    declared.deletes_rows_from |= allowed

    try:
        command.upgrade(cfg, 'head')
        landed = current_revision(path)
        if landed != head:
            raise RuntimeError(
                f'alembic_version is {landed} after upgrading to {head}; a '
                "migration committed alembic's transaction (use autocommit_block())"
            )
        lost = lost_rows(before, row_counts(path), declared)
        if lost:
            raise RuntimeError(
                f'migrating {current} -> {head} deleted rows (table: before, after): '
                f'{lost}. If that is intended, the migration declares it: '
                'deletes_rows_from = {...} or renames = {...}'
            )
    except Exception:
        logger.exception('Migration failed; restoring %s from %s', path, backup)
        restore(backup, path)
        logger.error('Restored %s to %s', path, current_revision(path))
        return 1

    logger.info('Migrated %s -> %s; no table lost rows', current, head)
    prune('app-premigrate-', keep)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument(
        '--allow-row-loss',
        action='append',
        default=[],
        metavar='TABLE',
        help=(
            'a table that may lose rows, beyond what the migrations declare '
            '(repeatable; for a hand run on the VM)'
        ),
    )
    parser.add_argument(
        '--backup-only',
        action='store_true',
        help='take a snapshot (app-daily-*) and migrate nothing',
    )
    parser.add_argument(
        '--keep',
        type=int,
        default=10,
        help='snapshots of the same kind to keep, newest first (default 10)',
    )
    args = parser.parse_args(argv)
    # Its own handler: alembic's env.py runs fileConfig, which sets the root
    # logger to WARN partway through and would swallow everything after.
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if args.backup_only:
        backup = snapshot(database_path(), f'app-daily-{_timestamp()}.db')
        logger.info('Backed up %s to %s', database_path(), backup)
        prune('app-daily-', args.keep)
        return 0
    return migrate(set(args.allow_row_loss), args.keep)


if __name__ == '__main__':
    sys.exit(main())
