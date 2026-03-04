import asyncio
import json
import os
import random
import string
from pathlib import Path
from typing import Optional

import pytest
from defusedxml import ElementTree

from lib.api import db


@pytest.fixture
def test_resources_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), 'resources'))


@pytest.fixture
def test_file_contents(test_resources_path):
    def _loader(file_name, mode='r'):
        with open(os.path.join(test_resources_path, file_name), mode) as file:
            return file.read()

    return _loader


@pytest.fixture
def db_session(monkeypatch, tmpdir):
    db.env.CAA_ROOT = str(tmpdir)
    db.env.SQLLITE_DIR = ''
    monkeypatch.setattr(db, '_engine', None)
    monkeypatch.setattr(db, '_session_factory', None)
    session_local = db.get_sessionmaker()
    session: Session = session_local()
    yield session
    session.rollback()
    session.close()
