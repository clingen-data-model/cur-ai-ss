"""Streamlit authentication gate.

Uses streamlit-authenticator's prebuilt **login** widget — local password
validation against in-memory hashes is unavoidable there — but every *mutation*
of the users table goes through the tested API:

- registration posts to ``/auth/register``
- password changes post to ``/auth/change-password`` (authenticated by the JWT
  we mint below)

The `users` table stays the single source of truth: the credentials dict handed
to stauth is an in-memory view loaded from the DB on each run. After a successful
login we mint a JWT (the same kind the API issues) so `lib/ui/api.py` can call
the token-protected endpoints.

stauth and `lib/core/security` both hash with bcrypt, so a user created via the
API is interchangeable with one validated here.
"""

import requests
import streamlit as st
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.exceptions import LoginError

from lib.api.db import session_scope
from lib.core.environment import env
from lib.core.security import create_access_token
from lib.models import UserDB
from lib.models.user import _EMAIL_RE
from lib.ui.api import (
    AUTH_TOKEN_KEY,
    change_password,
    get_http_error_detail,
    register,
)

COOKIE_NAME = 'caa_auth'
# Days the stauth re-auth cookie persists. The minted JWT is re-issued on every
# run (see require_auth), so this can outlive the JWT's expiry safely.
COOKIE_EXPIRY_DAYS = 7.0

MIN_PASSWORD_LENGTH = 8


def _load_credentials() -> dict:
    """Build stauth's credentials structure from active users only."""
    with session_scope() as session:
        users = session.query(UserDB).filter(UserDB.is_active.is_(True)).all()
        return {
            'usernames': {
                user.email: {
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'password': user.hashed_password,  # already a bcrypt hash
                }
                for user in users
            }
        }


def _render_request_access_form() -> None:
    with st.expander('Need access? Request it here!'):
        if st.session_state.get('_request_access_submitted'):
            st.success('Request submitted — an admin will review your request.')
        else:
            with st.form('request_access_form'):
                first_name = st.text_input('First name')
                last_name = st.text_input('Last name')
                email = st.text_input('Email')
                description_of_use_case = st.text_area('Describe your use case')
                submitted = st.form_submit_button('Request access')
    
            if not submitted:
                return
            if not (first_name and last_name and email and description_of_use_case):
                st.error('All fields are required.')
            elif not _EMAIL_RE.match(email.strip()):
                st.error('Please enter a valid email address.')
            else:
                try:
                    register(email, first_name, last_name, description_of_use_case)
                    st.session_state['_request_access_submitted'] = True
                    st.rerun()
                except requests.HTTPError as e:
                    st.error(get_http_error_detail(e))
    

def _render_change_password_form() -> None:
    """Hand-rolled change-password form posting to /auth/change-password."""
    with st.sidebar.expander('Change password'):
        with st.form('change_password_form', clear_on_submit=True):
            current = st.text_input('Current password', type='password')
            new = st.text_input('New password', type='password')
            new_repeat = st.text_input('Repeat new password', type='password')
            submitted = st.form_submit_button('Update password')

        if not submitted:
            return
        if not (current and new):
            st.error('All fields are required.')
        elif new != new_repeat:
            st.error('New passwords do not match.')
        elif len(new) < MIN_PASSWORD_LENGTH:
            st.error(f'Password must be at least {MIN_PASSWORD_LENGTH} characters.')
        else:
            try:
                change_password(current, new)
                st.success('Password updated.')
            except requests.HTTPError as e:
                st.error(get_http_error_detail(e))


def require_auth() -> None:
    """Block the app until the user is authenticated.

    Renders the login (and registration) widgets and calls ``st.stop()`` when
    unauthenticated. On success, stores a freshly minted JWT in session state and
    renders logout / change-password controls in the sidebar.
    """
    credentials = _load_credentials()
    authenticator = stauth.Authenticate(
        credentials,
        COOKIE_NAME,
        env.JWT_SECRET_KEY,
        COOKIE_EXPIRY_DAYS,
        auto_hash=False,  # passwords from the DB are already bcrypt-hashed
    )

    # Constrain the login/registration widgets to a centered column so they
    # don't stretch across the full screen width.
    _, center, _ = st.columns([1, 1.5, 1])
    with center:
        try:
            authenticator.login(location='main')
        except LoginError as e:
            st.error(str(e))

        status = st.session_state.get('authentication_status')
        if status is not True:
            # Clear any stale token and offer access request below the login form.
            st.session_state.pop(AUTH_TOKEN_KEY, None)
            if status is False:
                st.error('Email/password is incorrect')
            _render_request_access_form()
            st.stop()

    # Authenticated: resolve the user and mint a JWT for the API layer.
    username = st.session_state.get('username')
    with session_scope() as session:
        user = session.query(UserDB).filter(UserDB.email == username).one_or_none()
        if user is None or not user.is_active:
            st.session_state.pop(AUTH_TOKEN_KEY, None)
            st.error('Your account could not be found. Please sign in again.')
            authenticator.logout(location='unrendered')
            st.stop()
        st.session_state[AUTH_TOKEN_KEY] = create_access_token(user.id)
        display_name = f'{user.first_name} {user.last_name}'.strip() or user.email

    st.sidebar.markdown(f'Signed in as **{display_name}**')
    authenticator.logout('Log out', 'sidebar')
    _render_change_password_form()
