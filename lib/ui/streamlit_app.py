import streamlit as st

pg = st.navigation(
    pages=[
        st.Page('dashboard.py'),
        st.Page('details.py'),
    ],
    position='hidden',
)
pg.run()
