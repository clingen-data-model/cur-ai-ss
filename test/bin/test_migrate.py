"""lib.bin.migrate backs the database up, migrates it to head, and puts the backup
back when a migration loses rows or leaves alembic_version behind."""

import shutil
import sqlite3
from contextlib import closing

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from lib.api import db
from lib.bin import migrate as script


@pytest.fixture(autouse=True)
def database(monkeypatch, tmp_path):
    monkeypatch.setattr(db.env, 'CAA_ROOT', str(tmp_path))
    monkeypatch.setattr(db.env, 'SQLLITE_DIR', '')
    monkeypatch.setattr(db, '_engine', None)
    monkeypatch.setattr(db, '_session_factory', None)
    yield
    if db._engine is not None:
        db._engine.dispose()


def _previous_revision() -> str:
    cfg = script.alembic_config()
    head = ScriptDirectory.from_config(cfg).get_revision(script.head_revision(cfg))
    return head.down_revision


def _behind_head_with_genes() -> str:
    """A database one revision behind head, holding two genes."""
    previous = _previous_revision()
    command.upgrade(script.alembic_config(), previous)
    db.get_engine().dispose()
    with closing(sqlite3.connect(script.database_path())) as connection:
        connection.executemany(
            'INSERT INTO genes (symbol) VALUES (?)', [('GENE1',), ('GENE2',)]
        )
        connection.commit()
    return previous


def _genes() -> int:
    return script.row_counts(script.database_path())['genes']


def _backups(prefix: str) -> list[str]:
    if not script.backup_dir().exists():
        return []
    return sorted(p.name for p in script.backup_dir().glob(f'{prefix}*.db'))


def test_a_missing_database_is_created_at_head():
    assert script.main([]) == 0
    head = script.head_revision(script.alembic_config())
    assert script.current_revision(script.database_path()) == head


def test_a_database_at_head_is_left_alone():
    command.upgrade(script.alembic_config(), 'head')

    assert script.main([]) == 0
    assert _backups('app-premigrate-') == []


def test_a_clean_migration_backs_up_first_and_lands_on_head():
    previous = _behind_head_with_genes()

    assert script.main([]) == 0

    head = script.head_revision(script.alembic_config())
    assert script.current_revision(script.database_path()) == head
    assert _genes() == 2
    (backup,) = _backups('app-premigrate-')
    assert backup.endswith(f'-{previous}.db')
    backup_path = script.backup_dir() / backup
    assert script.current_revision(backup_path) == previous
    assert script.row_counts(backup_path)['genes'] == 2


def _upgrade_then_delete_genes(cfg, revision):
    """A migration that loses rows, as the CASCADE incidents did."""
    real_upgrade(cfg, revision)
    db.get_engine().dispose()
    with closing(sqlite3.connect(script.database_path())) as connection:
        connection.execute('DELETE FROM genes')
        connection.commit()


real_upgrade = command.upgrade


def test_lost_rows_restore_the_backup(monkeypatch):
    previous = _behind_head_with_genes()
    monkeypatch.setattr(script.command, 'upgrade', _upgrade_then_delete_genes)

    assert script.main([]) == 1

    assert script.current_revision(script.database_path()) == previous
    assert _genes() == 2


def test_a_table_allowed_to_lose_rows_does_not_fail(monkeypatch):
    _behind_head_with_genes()
    monkeypatch.setattr(script.command, 'upgrade', _upgrade_then_delete_genes)

    assert script.main(['--allow-row-loss', 'genes']) == 0
    assert _genes() == 0


def test_a_version_left_behind_restores_the_backup(monkeypatch):
    """The connection.commit() escape: the DDL ran, alembic_version did not move."""
    previous = _behind_head_with_genes()

    def upgrade_but_leave_the_version(cfg, revision):
        db.get_engine().dispose()
        with closing(sqlite3.connect(script.database_path())) as connection:
            connection.execute('CREATE TABLE stray (id INTEGER)')
            connection.commit()

    monkeypatch.setattr(script.command, 'upgrade', upgrade_but_leave_the_version)

    assert script.main([]) == 1

    assert script.current_revision(script.database_path()) == previous
    assert 'stray' not in script.row_counts(script.database_path())


def test_a_failing_migration_restores_the_backup(monkeypatch):
    previous = _behind_head_with_genes()

    def upgrade_then_fail(cfg, revision):
        _upgrade_then_delete_genes(cfg, revision)
        raise RuntimeError('migration blew up')

    monkeypatch.setattr(script.command, 'upgrade', upgrade_then_fail)

    assert script.main([]) == 1
    assert script.current_revision(script.database_path()) == previous
    assert _genes() == 2


def test_backup_only_snapshots_and_keeps_the_newest(monkeypatch):
    command.upgrade(script.alembic_config(), 'head')
    stamps = iter(['20260101T000000Z', '20260102T000000Z', '20260103T000000Z'])
    monkeypatch.setattr(script, '_timestamp', lambda: next(stamps))

    for _ in range(3):
        assert script.main(['--backup-only', '--keep', '2']) == 0

    assert _backups('app-daily-') == [
        'app-daily-20260102T000000Z.db',
        'app-daily-20260103T000000Z.db',
    ]
    head = script.head_revision(script.alembic_config())
    assert (
        script.current_revision(script.backup_dir() / _backups('app-daily-')[0]) == head
    )


def test_the_api_refuses_a_database_behind_head_when_not_migrating(monkeypatch):
    """With MIGRATE_ON_STARTUP off (dev-caa), the API leaves migrating to
    bin/migrate and will not start on a database it would have migrated."""
    import asyncio

    from lib.api.app import app, lifespan

    previous = _behind_head_with_genes()
    monkeypatch.setattr(db.env, 'MIGRATE_ON_STARTUP', False)

    async def start():
        async with lifespan(app):
            pass

    with pytest.raises(RuntimeError, match='run bin/migrate first'):
        asyncio.run(start())
    assert script.current_revision(script.database_path()) == previous


# --- What a migration declares: deletes_rows_from and renames ---


def test_lost_rows_follows_renames_and_declared_deletes():
    before = {'genes': 3, 'flags': 5, 'pedigrees': 4, 'dropped': 9}
    after = {'genes': 3, 'flags': 1, 'figure_descriptions': 2}

    nothing_declared = script.DeclaredChanges()
    assert script.lost_rows(before, after, nothing_declared) == {'flags': (5, 1)}

    renamed = script.DeclaredChanges(renames={'pedigrees': 'figure_descriptions'})
    assert script.lost_rows(before, after, renamed) == {
        'flags': (5, 1),
        'pedigrees -> figure_descriptions': (4, 2),
    }

    declared = script.DeclaredChanges(
        deletes_rows_from={'flags', 'figure_descriptions'},
        renames={'pedigrees': 'figure_descriptions'},
    )
    assert script.lost_rows(before, after, declared) == {}


_MIGRATION = """from alembic import op
revision = {revision!r}
down_revision = {down_revision!r}
branch_labels = None
depends_on = None
{declarations}

def upgrade():
{body}

def downgrade():
    pass
"""


@pytest.fixture
def extra_migrations(monkeypatch, tmp_path):
    """A copy of migrations/ that takes extra revisions on top of head, which
    bin/migrate then runs. Returns a function adding one; each goes on the last."""
    location = tmp_path / 'migrations'
    shutil.copytree(
        script.REPO_ROOT / 'migrations',
        location,
        ignore=shutil.ignore_patterns('__pycache__'),
    )
    cfg = script.alembic_config()
    cfg.set_main_option('script_location', str(location))
    monkeypatch.setattr(script, 'alembic_config', lambda: cfg)
    tip = [script.head_revision(cfg)]

    def add(revision: str, body: str, declarations: str = '') -> None:
        (location / 'versions' / f'{revision}.py').write_text(
            _MIGRATION.format(
                revision=revision,
                down_revision=tip[0],
                declarations=declarations,
                body='\n'.join(f'    {line}' for line in body.splitlines()),
            )
        )
        tip[0] = revision

    return add


def _at_head_with_genes():
    command.upgrade(script.alembic_config(), 'head')
    db.get_engine().dispose()
    with closing(sqlite3.connect(script.database_path())) as connection:
        connection.executemany(
            'INSERT INTO genes (symbol) VALUES (?)', [('GENE1',), ('GENE2',)]
        )
        connection.commit()


def test_a_declared_deletion_migrates(extra_migrations):
    _at_head_with_genes()
    extra_migrations(
        'zz_delete', "op.execute('DELETE FROM genes')", "deletes_rows_from = {'genes'}"
    )

    assert script.main([]) == 0
    assert script.current_revision(script.database_path()) == 'zz_delete'
    assert _genes() == 0


def test_an_undeclared_deletion_is_restored(extra_migrations):
    _at_head_with_genes()
    head = script.current_revision(script.database_path())
    extra_migrations('zz_delete', "op.execute('DELETE FROM genes')")

    assert script.main([]) == 1
    assert script.current_revision(script.database_path()) == head
    assert _genes() == 2


def test_a_declared_rename_is_compared_under_its_new_name(extra_migrations):
    """Two renames in one deploy chain: genes -> loci -> symbols. The rows are
    compared under the last name, so rows lost in the renamed table still fail."""
    _at_head_with_genes()
    head = script.current_revision(script.database_path())
    extra_migrations(
        'zz_rename1', "op.rename_table('genes', 'loci')", "renames = {'genes': 'loci'}"
    )
    extra_migrations(
        'zz_rename2',
        "op.rename_table('loci', 'symbols')\nop.execute('DELETE FROM symbols')",
        "renames = {'loci': 'symbols'}",
    )

    assert script.main([]) == 1
    assert script.current_revision(script.database_path()) == head
    assert _genes() == 2


def test_a_declared_rename_that_keeps_its_rows_migrates(extra_migrations):
    _at_head_with_genes()
    extra_migrations(
        'zz_rename', "op.rename_table('genes', 'loci')", "renames = {'genes': 'loci'}"
    )

    assert script.main([]) == 0
    assert script.row_counts(script.database_path())['loci'] == 2
