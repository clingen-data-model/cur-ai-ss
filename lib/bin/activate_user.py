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
    first_name = None
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
        first_name = user.first_name

    plain = (
        f'Hi {first_name},\n\n'
        'Your CAA account has been activated. You can now sign in with:\n\n'
        f'  Email:    {email}\n'
        f'  Password: {password}\n\n'
        'Please change your password in the sidebar after your first login.\n\n'
        'Sign in at https://gene-curation-ai.app\n'
    )
    html = (
        f'<p>Hi {first_name},</p>'
        '<p>Your CAA account has been activated. You can now sign in with:</p>'
        '<table>'
        f'<tr><td><b>Email</b></td><td>{email}</td></tr>'
        f'<tr><td><b>Password</b></td><td>{password}</td></tr>'
        '</table>'
        '<p>Please change your password in the sidebar after your first login.</p>'
        '<p><a href="https://gene-curation-ai.app">Sign in to CAA</a></p>'
    )
    send_email(
        to=email,
        subject='Your CAA account has been activated',
        body=plain,
        html=html,
    )
    print(f'Activated {email} and sent credentials email.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} <email>', file=sys.stderr)
        sys.exit(1)
    activate_user(sys.argv[1])
