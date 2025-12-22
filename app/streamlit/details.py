import requests
import streamlit as st

from app.models import ExtractionStatus, PaperResp
from app.streamlit.api import get_http_error_detail, get_paper, requeue_paper
from lib.evagg.types.base import Paper

paper_id = st.query_params.get('paper_id')

st.set_page_config(page_title='Curation Details', layout='wide')
left, center, right = st.columns([2, 4, 2])
main = center.container()


with center:
    with st.spinner('Loading paper...'):
        try:
            paper_resp: PaperResp = get_paper(paper_id)
            st.title(f'📄 Details for {paper_resp.filename}')
            if paper_resp.extraction_status == ExtractionStatus.EXTRACTED:
                st.success('✅ PDF extraction completed successfully')
            elif paper_resp.extraction_status == ExtractionStatus.QUEUED:
                st.warning('⏳ PDF extraction is queued')
            elif paper_resp.extraction_status == ExtractionStatus.FAILED:
                st.error('❌ PDF extraction failed')

            with st.expander('View Full PDF'):
                paper = Paper(id=paper_resp.id)
                st.pdf(paper.pdf_raw_path)

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
