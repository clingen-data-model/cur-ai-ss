from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from lib.api.app import app
from lib.api.auth import get_current_user
from lib.api.db import get_session
from lib.models import UserDB


@pytest.fixture
def unauth_client(db_session):
    """TestClient with the real auth dependency (no current-user override).

    Use this for exercising the register/login/me flow and 401 behavior.
    """

    def override_get_session():
        yield db_session

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    # This overrides the app lifespan so it doesn't try to run migrations.
    # DB initialization for tests should be handled by the `db_session` fixture.
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.router.lifespan_context = original_lifespan


@pytest.fixture
def test_user(db_session):
    """A persisted user used as the authenticated editor in `client`."""
    user = UserDB(
        email='tester@example.com',
        hashed_password='not-a-real-hash',
        first_name='Test',
        last_name='User',
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def client(db_session, test_user):
    def override_get_session():
        yield db_session

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    # This overrides the app lifespan so it doesn't try to run migrations.
    # DB initialization for tests should be handled by the `db_session` fixture.
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[get_session] = override_get_session
    # Authenticated endpoints resolve to a fixed test user so existing tests do
    # not need to manage tokens; updated_by_user_id is recorded as this user.
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.router.lifespan_context = original_lifespan
