import streamlit as st

from lib.ui.auth import require_auth

# set_page_config must be the first Streamlit command in a run, and it can only
# be called once — so it lives here (before the auth gate renders any widgets)
# rather than in the individual pages.
st.set_page_config(page_title='Gene Curation', layout='wide')

require_auth()  # renders login/register and st.stop()s until authenticated

pg = st.navigation(
    pages=[
        st.Page('dashboard.py'),
        st.Page('paper/header.py', url_path='paper'),
    ],
    position='hidden',
)
pg.run()
