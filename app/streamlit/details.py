import requests
import streamlit as st

from app.models import ExtractionStatus
from app.streamlit.api import get_http_error_detail, get_paper, requeue_paper

paper_id = st.query_params.get('paper_id')

st.set_page_config(page_title='Curation Details', layout='wide')
left, center, right = st.columns([2, 4, 2])
main = center.container()


with center:
    with st.spinner('Loading paper...'):
        try:
            paper = get_paper(paper_id)
            st.title(f'📄 Details for {paper["filename"]}')
            if paper['extraction_status'] == ExtractionStatus.EXTRACTED:
                st.success('✅ PDF extraction completed successfully')
            elif paper['extraction_status'] == ExtractionStatus.QUEUED:
                st.warning('⏳ PDF extraction is queued')
            elif paper['extraction_status'] == ExtractionStatus.FAILED:
                st.error('❌ PDF extraction failed')

            with st.expander('View Full PDF'):
                st.pdf(paper['raw_path'])

            # Reset Button
            if st.button('🔄 Rerun EvAGG', use_container_width=True):
                try:
                    requeue_paper(paper_id)
                    st.toast('EvAGG Job Queued', icon=':material/thumb_up:')
                except requests.HTTPError as e:
                    if e.response.status_code == 409:
                        icon = '⏳'
                    else:
                        icon = '❌'
                    st.toast(
                        f'Failed to refresh job: {get_http_error_detail(e)}', icon=icon
                    )
                except Exception as e:
                    st.toast(str(e))
        except requests.HTTPError as e:
            st.error(f'Failed to load paper: {get_http_error_detail(e)}')
        except Exception as e:
            st.error(str(e))

with st.sidebar:
    st.page_link('dashboard.py', label='Curation Dashboard', icon='🏠')
