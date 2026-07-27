"""Password hashing and JWT access-token helpers.

All cryptographic operations for authentication live here so the rest of the
codebase never touches ``bcrypt`` or ``jwt`` directly.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from lib.core.environment import env


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt, returning a UTF-8 encoded digest."""
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if the plaintext password matches the stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), hashed_password.encode('utf-8')
    )


def create_access_token(user_id: int) -> str:
    """Create a signed JWT access token whose subject is the user's id."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=env.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {'sub': str(user_id), 'exp': expire}
    return jwt.encode(payload, env.JWT_SECRET_KEY, algorithm=env.JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Decode and validate a JWT access token, returning the user id.

    Raises ``jwt.InvalidTokenError`` (or a subclass) if the token is expired,
    malformed, or otherwise invalid.
    """
    payload = jwt.decode(token, env.JWT_SECRET_KEY, algorithms=[env.JWT_ALGORITHM])
    subject = payload.get('sub')
    if subject is None:
        raise jwt.InvalidTokenError('Token missing subject claim')
    return int(subject)
