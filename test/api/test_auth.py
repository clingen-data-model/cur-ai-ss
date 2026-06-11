import pytest

from lib.core.security import hash_password
from lib.models import UserDB

_REGISTER_PAYLOAD = {
    'email': 'newuser@example.com',
    'first_name': 'New',
    'last_name': 'User',
    'description_of_use_case': 'Testing the registration flow.',
}

_KNOWN_PASSWORD = 'supersecret'


def _seed_active_user(db_session, email: str = 'newuser@example.com') -> UserDB:
    """Create an active user with a known password directly in the DB."""
    user = UserDB(
        email=email,
        hashed_password=hash_password(_KNOWN_PASSWORD),
        first_name='New',
        last_name='User',
        description_of_use_case='Test user.',
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _register_and_login(unauth_client, db_session) -> str:
    """Seed an active user with a known password and return a bearer token."""
    _seed_active_user(db_session)
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': _KNOWN_PASSWORD},
    )
    return resp.json()['access_token']


def test_register_creates_inactive_user(unauth_client):
    resp = unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body['email'] == 'newuser@example.com'
    assert body['is_active'] is False
    assert (
        body['description_of_use_case'] == _REGISTER_PAYLOAD['description_of_use_case']
    )
    assert 'hashed_password' not in body


def test_inactive_user_cannot_login(db_session, unauth_client):
    user = UserDB(
        email='inactive@example.com',
        hashed_password=hash_password(_KNOWN_PASSWORD),
        first_name='Inactive',
        last_name='User',
        description_of_use_case='',
        is_active=False,
    )
    db_session.add(user)
    db_session.flush()
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'inactive@example.com', 'password': _KNOWN_PASSWORD},
    )
    assert resp.status_code == 401


def test_active_user_can_login_and_access_me(unauth_client, db_session):
    _seed_active_user(db_session)
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': _KNOWN_PASSWORD},
    )
    assert resp.status_code == 200
    token = resp.json()['access_token']

    resp = unauth_client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.json()['email'] == 'newuser@example.com'


def test_register_duplicate_email_conflicts(unauth_client):
    first = unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    assert first.status_code == 201
    dup = unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    assert dup.status_code == 409


def test_login_wrong_password_unauthorized(unauth_client, db_session):
    _seed_active_user(db_session)
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': 'wrong-password'},
    )
    assert resp.status_code == 401


def test_change_password_flow(unauth_client, db_session):
    token = _register_and_login(unauth_client, db_session)
    auth = {'Authorization': f'Bearer {token}'}

    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': _KNOWN_PASSWORD, 'new_password': 'brand-new-pw'},
        headers=auth,
    )
    assert resp.status_code == 200

    # Old password no longer works; new one does.
    old = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': _KNOWN_PASSWORD},
    )
    assert old.status_code == 401
    new = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': 'brand-new-pw'},
    )
    assert new.status_code == 200


def test_change_password_wrong_current_unauthorized(unauth_client, db_session):
    token = _register_and_login(unauth_client, db_session)
    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': 'not-it', 'new_password': 'brand-new-pw'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 401


def test_change_password_rejects_short_new(unauth_client, db_session):
    token = _register_and_login(unauth_client, db_session)
    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': _KNOWN_PASSWORD, 'new_password': 'short'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 422


def test_change_password_requires_authentication(unauth_client):
    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': _KNOWN_PASSWORD, 'new_password': 'brand-new-pw'},
    )
    assert resp.status_code == 401


def test_me_requires_authentication(unauth_client):
    assert unauth_client.get('/auth/me').status_code == 401
    bad = unauth_client.get(
        '/auth/me', headers={'Authorization': 'Bearer not-a-real-token'}
    )
    assert bad.status_code == 401


# ---------------------------------------------------------------------------
# Activate endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db_session):
    user = UserDB(
        email='admin@example.com',
        hashed_password=hash_password(_KNOWN_PASSWORD),
        first_name='Admin',
        last_name='User',
        description_of_use_case='',
        is_active=True,
        is_admin=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def admin_token(unauth_client, admin_user):
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'admin@example.com', 'password': _KNOWN_PASSWORD},
    )
    return resp.json()['access_token']


def test_activate_user(unauth_client, db_session, admin_token):
    unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    user = db_session.query(UserDB).filter_by(email='newuser@example.com').one()
    assert user.is_active is False

    resp = unauth_client.post(
        f'/auth/activate/{user.id}',
        headers={'Authorization': f'Bearer {admin_token}'},
    )
    assert resp.status_code == 200
    assert resp.json()['is_active'] is True

    db_session.refresh(user)
    assert user.is_active is True


def test_activate_already_active_conflicts(unauth_client, db_session, admin_token):
    active = _seed_active_user(db_session)
    resp = unauth_client.post(
        f'/auth/activate/{active.id}',
        headers={'Authorization': f'Bearer {admin_token}'},
    )
    assert resp.status_code == 409


def test_activate_unknown_user_not_found(unauth_client, admin_token):
    resp = unauth_client.post(
        '/auth/activate/99999',
        headers={'Authorization': f'Bearer {admin_token}'},
    )
    assert resp.status_code == 404


def test_activate_requires_admin(unauth_client, db_session):
    unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    pending = db_session.query(UserDB).filter_by(email='newuser@example.com').one()

    # Non-admin active user cannot activate.
    non_admin = _seed_active_user(db_session, email='plain@example.com')
    resp = unauth_client.post(
        '/auth/login', json={'email': non_admin.email, 'password': _KNOWN_PASSWORD}
    )
    token = resp.json()['access_token']

    resp = unauth_client.post(
        f'/auth/activate/{pending.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 403


def test_activate_requires_authentication(unauth_client, db_session):
    unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    pending = db_session.query(UserDB).filter_by(email='newuser@example.com').one()
    resp = unauth_client.post(f'/auth/activate/{pending.id}')
    assert resp.status_code == 401
