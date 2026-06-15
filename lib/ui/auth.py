"""Streamlit authentication gate.

All auth operations go through the API:
- login posts to ``/auth/login`` and receives a JWT
- registration posts to ``/auth/register``
- password changes post to ``/auth/change-password``

The JWT is persisted in a browser cookie (via extra-streamlit-components
CookieManager) so page refreshes don't require re-login.
"""

import time

import requests
import streamlit as st
from extra_streamlit_components import CookieManager

from lib.models.user import _EMAIL_RE, UserResp
from lib.ui.api import (
    AUTH_TOKEN_KEY,
    change_password,
    get_http_error_detail,
    get_me,
    login,
    register,
)

MIN_PASSWORD_LENGTH = 8
_CURRENT_USER_KEY = '_current_user'


def _render_login_form(cookies: CookieManager) -> None:
    with st.form('login_form'):
        email = st.text_input('Email')
        password = st.text_input('Password', type='password')
        submitted = st.form_submit_button('Sign in')

    if not submitted:
        return
    try:
        token = login(email, password)
        st.session_state[AUTH_TOKEN_KEY] = token
        st.session_state[_CURRENT_USER_KEY] = get_me()
        st.session_state.pop('_logged_out', None)
        # Write the cookie last and give the component a beat to flush the
        # write to the browser before st.rerun() restarts the script — the
        # CookieManager set is async and an immediate rerun drops it.
        cookies.set(AUTH_TOKEN_KEY, token)
        time.sleep(2)
        st.rerun()
    except requests.HTTPError:
        st.error('Email/password is incorrect.')


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


def _render_change_password_form(container: st.delta_generator.DeltaGenerator) -> None:
    with container.expander('Change password'):
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

    Renders login and request-access widgets and calls ``st.stop()`` when
    unauthenticated. On success, stores the API-issued JWT in session state and
    a browser cookie, and renders logout / change-password controls in the sidebar.
    """
    cookies: CookieManager = CookieManager()
    # The CookieManager renders a frontend component that reads the browser's
    # cookies and ships them back to Python. On the *first* script run of a new
    # session that round-trip hasn't happened yet, so cookies.get() returns None
    # for everyone — including returning users who hold a valid auth cookie.
    # Without this guard we'd fall through to the login form and force them to
    # re-authenticate on every fresh page load.
    #
    # So on the first run we just mount the component and st.stop(). Mounting it
    # makes the browser send the cookies back, which triggers an automatic rerun;
    # on that second run _auth_init is set, cookies.get() returns the stored
    # token, and the session is restored silently. The flag lives in session_state
    # so it resets per session (exactly when we need to wait for the component
    # again), not per rerun.
    if '_auth_init' not in st.session_state:
        st.session_state['_auth_init'] = True
        st.stop()

    # Restore token from cookie into session state on fresh page load. Skipped
    # after an explicit logout: the cookie deletion takes a render to propagate
    # to the browser, so re-reading it here would resurrect the stale token.
    if AUTH_TOKEN_KEY not in st.session_state and not st.session_state.get(
        '_logged_out'
    ):
        token = cookies.get(AUTH_TOKEN_KEY)
        if token:
            st.session_state[AUTH_TOKEN_KEY] = token
            try:
                st.session_state[_CURRENT_USER_KEY] = get_me()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 401:
                    # Token expired or revoked — clear and re-prompt.
                    cookies.delete(AUTH_TOKEN_KEY)
                    st.session_state.pop(AUTH_TOKEN_KEY, None)
                # Any other error (server-side 5xx): keep the token and proceed.

    if AUTH_TOKEN_KEY not in st.session_state:
        _, center, _ = st.columns([1, 1.5, 1])
        with center:
            _render_login_form(cookies)
            _render_request_access_form()
        st.stop()

    user: UserResp | None = st.session_state.get(_CURRENT_USER_KEY)
    if user:
        full_name = f'{user.first_name} {user.last_name}'.strip()
        display_name = f'{full_name} ({user.email})' if full_name else user.email
    else:
        display_name = ''
    st.sidebar.markdown(f'Signed in as **{display_name}**')
    pw_col, logout_col = st.sidebar.columns(2)
    if logout_col.button('Log out', use_container_width=True):
        st.session_state.pop(AUTH_TOKEN_KEY, None)
        st.session_state.pop(_CURRENT_USER_KEY, None)
        st.session_state['_logged_out'] = True
        if cookies.get(AUTH_TOKEN_KEY):
            cookies.delete(AUTH_TOKEN_KEY)
            time.sleep(2)
        st.rerun()
    _render_change_password_form(pw_col)
