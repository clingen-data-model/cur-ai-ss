import json
import streamlit as st
import random

from lib.evagg.app import SinglePMIDApp


@st.cache_data(show_spinner="Running EvAGG...")
def run_app(pmid: str, gene_symbol: str, cache_bust: int):
    app = SinglePMIDApp(
        pmid,
        gene_symbol,
    )
    return app.execute()


st.set_page_config(page_title="cur-ai-ious", layout="wide")
st.title("cur-ai-ious")

# Initialize session state
if "curation_data" not in st.session_state:
    st.session_state.curation_data = []

# Input fields
with st.form(key="my_form"):
    pmid = st.text_input("Enter PubMed ID (PMID):")
    gene_symbol = st.text_input("Enter Gene Symbol:")
    override_cache = st.checkbox("Override Caching")
    submitted = st.form_submit_button("Submit")

if submitted:
    if not pmid or not gene_symbol:
        st.error("Please enter both a PMID and a gene symbol.")
    else:
        st.session_state.curation_data = run_app(
            pmid, gene_symbol, random.randint(0, int(1e9)) if override_cache else 0
        )
        st.success("Fetched data from API!")

# Display JSON in an expander with a spinner
if st.session_state.curation_data:
    with st.expander("View Result as JSON"):
        st.json(st.session_state.curation_data, expanded=True)
        st.download_button(
            label="Download JSON",
            data=json.dumps(st.session_state.curation_data, indent=2),
            file_name="curation_data.json",
            mime="application/json",
        )
