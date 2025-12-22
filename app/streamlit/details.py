import requests
import streamlit as st

from app.streamlit.api import get_paper, requeue_paper, get_http_error_detail
from app.models import ExtractionStatus

paper_id = st.query_params.get('paper_id')

st.set_page_config(page_title='Curation Details', layout='wide')
left, center, right = st.columns([2, 3, 2])
main = center.container()


with center:
    with st.spinner('Loading paper...'):
        try:
            paper = get_paper(paper_id)
            st.title(f'📄 Details for {paper['filename']}')
            col_msg, col_btn = st.columns([6, 1])
            with col_msg:
                if paper['status'] == ExtractionStatus.EXTRACTED:
                    st.success("✅ PDF extraction completed successfully")
                elif paper['status'] == ExtractionStatus.QUEUED:
                    st.warning("⏳ PDF extraction is queued")
                elif paper['status'] == ExtractionStatus.FAILED:
                    st.error("❌ PDF extraction failed")
            with col_btn:
                if st.button("🔄 Rerun EvAGG", use_container_width=True):
                    try:
                        requeue_paper(paper_id)
                        st.toast("Job refreshed")
                    except Exception as e:
                        st.error(f"Failed to refresh job: {e}")
                    st.rerun()
        except requests.HTTPError as e:
            st.error(f'Failed to load paper: {get_http_error_detail(e)}')
        except Exception as e:
            st.error(str(e))

with st.sidebar:
    st.page_link("dashboard.py", label="Curation Dashboard", icon="🏠")
