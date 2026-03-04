from pathlib import Path

from alembic import command
from alembic.config import Config


def test_alembic_upgrade_head(monkeypatch, tmp_path):
    """Simple test that all migrations apply cleanly on a fresh DB."""
    from lib.api import db

    monkeypatch.setattr(db.env, 'CAA_ROOT', str(tmp_path))
    monkeypatch.setattr(db.env, 'SQLLITE_DIR', '')
    monkeypatch.setattr(db, '_engine', None)
    monkeypatch.setattr(db, '_session_factory', None)

    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / 'alembic.ini'))
    command.upgrade(cfg, 'head')
