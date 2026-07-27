import jwt
import pytest

from lib.core import security
from lib.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password('correct horse battery staple')
    assert hashed != 'correct horse battery staple'  # not stored in plaintext
    assert verify_password('correct horse battery staple', hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password('the-right-one')
    assert verify_password('the-wrong-one', hashed) is False


def test_hash_password_is_salted():
    # bcrypt salts each hash, so the same input yields different digests.
    assert hash_password('same-input') != hash_password('same-input')


def test_access_token_roundtrip():
    token = create_access_token(user_id=42)
    assert decode_access_token(token) == 42


def test_decode_rejects_tampered_token():
    token = create_access_token(user_id=7)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token + 'tampered')


def test_decode_rejects_expired_token(monkeypatch):
    # Token that expired in the past.
    monkeypatch.setattr(security.env, 'ACCESS_TOKEN_EXPIRE_MINUTES', -1)
    token = create_access_token(user_id=1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
