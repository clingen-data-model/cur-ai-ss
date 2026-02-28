import streamlit as st

pg = st.navigation(
    pages=[
        st.Page('dashboard.py'),
        st.Page('paper/pdf.py', url_path='paper-pdf'),
        st.Page('paper/metadata.py', url_path='paper-metadata'),
        st.Page('paper/patients.py', url_path='paper-patients'),
        st.Page('paper/variants.py', url_path='paper-variants'),
    ],
    position='hidden',
)
pg.run()
