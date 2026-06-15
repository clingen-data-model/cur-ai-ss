import streamlit as st

from lib.ui.auth import require_auth

# set_page_config must be the first Streamlit command in a run, and it can only
# be called once — so it lives here (before the auth gate renders any widgets)
# rather than in the individual pages.
st.set_page_config(page_title='Gene Curation', layout='wide')

# Declare navigation BEFORE the auth gate, and keep pg.run() AFTER it.
#
# A full page load (clicking a dashboard LinkColumn link, or refreshing /paper)
# starts a fresh session, so require_auth() hits its first-run st.stop() (see the
# _auth_init guard there). Anything st.stop()'d before st.navigation() runs loses
# the current route — Streamlit reverts the URL to the default page (the
# dashboard). Declaring the pages here every run keeps the URL (e.g. /paper)
# resolved across that stop.
#
# st.navigation() only declares the pages and resolves which matches the URL; it
# renders no page content. The page body runs only at pg.run(), which stays below
# require_auth() — so an unauthenticated user is still stopped at the login form
# and never sees a page.
pg = st.navigation(
    pages=[
        st.Page('dashboard.py'),
        st.Page('paper/header.py', url_path='paper'),
    ],
    position='hidden',
)

require_auth()  # renders login/register and st.stop()s until authenticated

pg.run()
