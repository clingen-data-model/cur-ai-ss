import streamlit as st

from lib.ui.auth import require_auth

# set_page_config must be the first Streamlit command in a run, and it can only
# be called once — so it lives here (before the auth gate renders any widgets)
# rather than in the individual pages.
st.set_page_config(
    page_title='Gene Curation',
    layout='wide',
    # An int here sets the sidebar's starting width in pixels (Streamlit clamps
    # it to 200-600) — wide enough that the change-password / log-out controls
    # aren't cramped. Users can still drag the sidebar edge; once they do, their
    # width is remembered in localStorage and wins over this default.
    initial_sidebar_state=380,
)

# Backstop for the above. Streamlit's frontend only reads initial_sidebar_width
# in a useState initializer, and a width previously stored in the browser's
# localStorage["sidebarWidth"] (written on every sidebar drag) takes precedence
# over it — so in practice the page-config value often loses and the sidebar
# falls back to its 300px default. This pins the floor in CSS instead.
#
# The [aria-expanded="true"] scope matters: the collapsed sidebar is hidden with
# a JS-computed transform: translateX(-<width>px). Forcing a width the JS doesn't
# know about leaves a sliver on screen and misplaces the ">>" expand control, so
# the override must drop away the moment the sidebar collapses. min-width (not
# width) also leaves users free to drag it wider.
st.markdown(
    """
    <style>
    section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 380px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
