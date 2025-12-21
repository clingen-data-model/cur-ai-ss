import requests
import streamlit as st

from app.streamlit.api import get_paper

paper_id = st.query_params.get('paper_id')

st.set_page_config(page_title='Papers Dashboard', layout='wide')
left, center, right = st.columns([2, 3, 2])
main = center.container()

with center:
    st.title(f'📄 Details for {paper_id}')
