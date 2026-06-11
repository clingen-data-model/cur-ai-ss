#!/usr/bin/env python3
"""Activate a pending user account and email them their temporary password.

Usage:
    uv run python -m lib.bin.activate_user <email>
"""

import secrets
import sys

from lib.api.db import session_scope
from lib.core.email import send_email
from lib.core.security import hash_password
from lib.models import UserDB


def activate_user(email: str) -> None:
    with session_scope() as session:
        user = session.query(UserDB).filter_by(email=email).one_or_none()
        if user is None:
            print(f'Error: no user found with email {email}', file=sys.stderr)
            sys.exit(1)
        if user.is_active:
            print(f'Error: {email} is already active', file=sys.stderr)
            sys.exit(1)

        password = secrets.token_urlsafe(16)
        user.hashed_password = hash_password(password)
        user.is_active = True

    send_email(
        to=user.email,
        subject='Your CAA account has been activated',
        body=(
            f'Hi {user.first_name},\n\n'
            'Your CAA account has been activated. You can now sign in with:\n\n'
            f'  Email:    {user.email}\n'
            f'  Password: {password}\n\n'
            'Please change your password in the sidebar after your first login.\n'
        ),
    )
    print(f'Activated {email} and sent credentials email.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} <email>', file=sys.stderr)
        sys.exit(1)
    activate_user(sys.argv[1])
