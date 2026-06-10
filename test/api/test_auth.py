_REGISTER_PAYLOAD = {
    'email': 'newuser@example.com',
    'password': 'supersecret',
    'first_name': 'New',
    'last_name': 'User',
}


def _register_and_login(unauth_client) -> str:
    """Register the standard test user and return a bearer token."""
    unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': 'supersecret'},
    )
    return resp.json()['access_token']


def test_register_login_me_flow(unauth_client):
    # Register
    resp = unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body['email'] == 'newuser@example.com'
    assert 'hashed_password' not in body  # never leak the hash

    # Login
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': 'supersecret'},
    )
    assert resp.status_code == 200
    token = resp.json()['access_token']
    assert token

    # Authenticated /auth/me
    resp = unauth_client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.json()['email'] == 'newuser@example.com'


def test_register_duplicate_email_conflicts(unauth_client):
    first = unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    assert first.status_code == 201
    dup = unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    assert dup.status_code == 409


def test_login_wrong_password_unauthorized(unauth_client):
    unauth_client.post('/auth/register', json=_REGISTER_PAYLOAD)
    resp = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': 'wrong-password'},
    )
    assert resp.status_code == 401


def test_change_password_flow(unauth_client):
    token = _register_and_login(unauth_client)
    auth = {'Authorization': f'Bearer {token}'}

    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': 'supersecret', 'new_password': 'brand-new-pw'},
        headers=auth,
    )
    assert resp.status_code == 200

    # Old password no longer works; new one does.
    old = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': 'supersecret'},
    )
    assert old.status_code == 401
    new = unauth_client.post(
        '/auth/login',
        json={'email': 'newuser@example.com', 'password': 'brand-new-pw'},
    )
    assert new.status_code == 200


def test_change_password_wrong_current_unauthorized(unauth_client):
    token = _register_and_login(unauth_client)
    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': 'not-it', 'new_password': 'brand-new-pw'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 401


def test_change_password_rejects_short_new(unauth_client):
    token = _register_and_login(unauth_client)
    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': 'supersecret', 'new_password': 'short'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 422


def test_change_password_requires_authentication(unauth_client):
    resp = unauth_client.post(
        '/auth/change-password',
        json={'current_password': 'supersecret', 'new_password': 'brand-new-pw'},
    )
    assert resp.status_code == 401


def test_me_requires_authentication(unauth_client):
    assert unauth_client.get('/auth/me').status_code == 401
    bad = unauth_client.get(
        '/auth/me', headers={'Authorization': 'Bearer not-a-real-token'}
    )
    assert bad.status_code == 401
