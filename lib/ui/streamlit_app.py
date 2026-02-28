import streamlit as st

pg = st.navigation(
    pages=[
        st.Page('dashboard.py'),
        st.Page('paper/header.py', title='Paper PDF'),
    ],
    position='hidden',
)
pg.run()
