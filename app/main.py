import streamlit as st
import json

st.set_page_config(page_title="cur-ai-ious", layout="wide")
st.title("cur-ai-ious")

# Initialize session state
if 'curation_data' not in st.session_state:
    st.session_state.curation_data = {}

# Input fields
pmid = st.text_input("Enter PubMed ID (PMID):")
gene_symbol = st.text_input("Enter Gene Symbol:")

# Submit button
if st.button("Submit"):
    if not pmid or not gene_symbol:
        st.warning("Please enter both a PMID and a gene symbol.")
    else:
        # Show spinner before updating session state
        with st.spinner("Processing submission..."):
            import time
            time.sleep(3)  # simulate processing delay
            st.session_state.curation_data = {
                "pmid": pmid,
                "gene": gene_symbol
            }
        st.success(f"PMID: {pmid}")
        st.success(f"Gene: {gene_symbol}")

# Display JSON in an expander with a spinner
if st.session_state.curation_data:
    with st.spinner("Loading result..."):
        time.sleep(1)  # simulate a brief delay for spinner effect
        with st.expander("View Result as JSON"):
            st.json(st.session_state.curation_data, expanded=True)
            st.download_button(
                label="Download JSON",
                data=json.dumps(st.session_state.curation_data, indent=2),
                file_name="curation_data.json",
                mime="application/json",
            )