"""FastAPI authentication dependencies."""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from lib.api.db import get_session
from lib.core.security import decode_access_token
from lib.models import UserDB

# auto_error=False so we can return our own 401 and support the optional variant.
_bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail='Could not validate credentials',
    headers={'WWW-Authenticate': 'Bearer'},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_session),
) -> UserDB:
    """Resolve the authenticated user from a bearer token, or raise 401."""
    if credentials is None:
        raise _CREDENTIALS_EXCEPTION
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise _CREDENTIALS_EXCEPTION

    user = session.get(UserDB, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXCEPTION
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_session),
) -> UserDB | None:
    """Like ``get_current_user`` but returns None instead of raising when no
    valid credentials are supplied. Used by endpoints that record ``updated_by``
    when a user is present but do not strictly require authentication."""
    if credentials is None:
        return None
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        return None
    user = session.get(UserDB, user_id)
    if user is None or not user.is_active:
        return None
    return user
