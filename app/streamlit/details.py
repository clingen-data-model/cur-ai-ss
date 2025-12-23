import requests
import streamlit as st
import time

from app.models import ExtractionStatus, PaperResp
from app.streamlit.api import (
    delete_paper,
    get_http_error_detail,
    get_paper,
    requeue_paper,
)
from lib.evagg.types.base import Paper

paper_id = st.query_params.get('paper_id')

st.set_page_config(page_title='Curation Details', layout='wide')
left, center, right = st.columns([2, 4, 2])

with center:
    with st.spinner('Loading paper...'):
        try:
            paper_resp: PaperResp = get_paper(paper_id)
            with st.container(horizontal=True, vertical_alignment='center'):
                st.title(f'📄 Details for {paper_resp.filename}')

                # Badge
                st.text('Current Status:')
                if paper_resp.extraction_status == ExtractionStatus.EXTRACTED:
                    st.badge('Success', icon=':material/check:', color='green')
                elif paper_resp.extraction_status == ExtractionStatus.QUEUED:
                    st.badge('Queued', icon='⏳', color='yellow')
                elif paper_resp.extraction_status == ExtractionStatus.FAILED:
                    st.badge('Failed', icon='❌', color='red')

                # Reset Button
                if st.button(
                    '🔄 Rerun EvAGG',
                    width='content',
                    type='tertiary',
                    help='Queues EvAGG to run, over-writing all curation data.',
                ):
                    try:
                        requeue_paper(paper_id)
                        st.toast('EvAGG Job Queued', icon=':material/thumb_up:')
                    except requests.HTTPError as e:
                        if e.response.status_code == 409:
                            icon = '⏳'
                        else:
                            icon = '❌'
                        st.toast(
                            f'Failed to Refresh EvAGG Job: {get_http_error_detail(e)}',
                            icon=icon,
                        )
                    except Exception as e:
                        st.toast(str(e))

                # Delete Button
                if st.button(
                    '🗑️ Delete Paper',
                    width='content',
                    type='tertiary',
                    help='Removes the paper and all curation data.',
                ):
                    try:
                        delete_paper(paper_id)
                        st.toast('Successfully deleted!', icon='🗑️')
                        time.sleep(0.5)
                        st.switch_page('dashboard.py')
                    except requests.HTTPError as e:
                        st.toast(f'Failed to Delete Paper: {get_http_error_detail(e)}')
                    except Exception as e:
                        st.toast(str(e))

            with st.expander('View Full PDF'):
                paper = Paper(id=paper_resp.id)
                st.pdf(paper.pdf_raw_path)
                st.divider()
                st.download_button(
                    label='Download PDF',
                    data=open(paper.pdf_raw_path, 'rb').read(),
                    icon=':material/download:',
                    mime='application/pdf',
                    width='stretch',
                )

        except requests.HTTPError as e:
            st.error(f'Failed to load paper: {get_http_error_detail(e)}')
        except Exception as e:
            st.error(str(e))

with st.sidebar:
    st.page_link('dashboard.py', label='Curation Dashboard', icon='🏠')
