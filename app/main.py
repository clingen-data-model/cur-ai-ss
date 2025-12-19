import json
import streamlit as st
import random

from lib.evagg.app import App


@st.cache_data(show_spinner='Running EvAGG...')
def run_app(content: bytes, gene_symbol: str, cache_bust: int):
    app = App(
        content,
        gene_symbol,
    )
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            return app.execute()
        except Exception as e:
            if attempt == max_attempts:
                st.exception(e)


st.set_page_config(page_title='cur-ai-ious', layout='wide')
st.title('cur-ai-ious')

# Initialize session state
if 'curation_data' not in st.session_state:
    st.session_state.curation_data = []

# Input fields
with st.form(key='my_form'):
    uploaded_file = st.file_uploader('Choose a PDF file', type='pdf')
    gene_symbol = st.text_input('Enter Gene Symbol:')
    override_cache = st.checkbox('Override Caching')
    submitted = st.form_submit_button('Submit')

if uploaded_file is not None:
    st.pdf(uploaded_file)

if submitted:
    if not uploaded_file or not gene_symbol:
        st.error('Please enter both a pdf and a gene symbol.')
    else:
        if res := run_app(
            uploaded_file.read(),
            gene_symbol,
            random.randint(0, int(1e9)) if override_cache else 0,
        ):
            st.session_state.curation_data = res
            st.success('Successfully executed EvAGG')

# Display JSON in an expander with a spinner
if st.session_state.curation_data:
    with st.expander('View Result as JSON'):
        st.json(st.session_state.curation_data, expanded=True)
        st.download_button(
            label='Download JSON',
            data=json.dumps(st.session_state.curation_data, indent=2),
            file_name='curation_data.json',
            mime='application/json',
        )
