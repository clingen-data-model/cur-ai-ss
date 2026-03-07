import streamlit as st

pg = st.navigation(
    pages=[
        st.Page('dashboard.py'),
        st.Page('paper/header.py', url_path='paper'),
    ],
    position='hidden',
)
pg.run()
