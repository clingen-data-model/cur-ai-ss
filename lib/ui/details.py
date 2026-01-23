import json
import time

import requests
import streamlit as st

from lib.evagg.types.base import Paper
from lib.models import ExtractionStatus, PaperResp
from lib.ui.api import (
    delete_paper,
    get_http_error_detail,
    get_paper,
    requeue_paper,
)
from lib.ui.helpers import paper_dict_to_markdown

paper_id = st.query_params.get('paper_id')
if paper_id is None:
    st.warning('No paper_id provided in URL.')
    st.stop()  # stop further execution

st.set_page_config(page_title='Curation Details', layout='wide')
left, center, right = st.columns([1, 5, 1])

with center:
    with st.spinner('Loading paper...'):
        try:
            paper_resp: PaperResp = get_paper(paper_id)
        except requests.HTTPError as e:
            st.error(f'Failed to load paper: {get_http_error_detail(e)}')
        except Exception as e:
            st.error(str(e))

    if paper_resp is None:
        st.stop()

    with st.container(horizontal=True, vertical_alignment='center'):
        st.title(f'📄 Details for {paper_resp.filename}')

        # Badge
        st.text('Current Status:')
        if paper_resp.extraction_status == ExtractionStatus.PARSED:
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
                time.sleep(0.5)
                st.rerun()
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

    tab1, tab2, tab3 = st.tabs(['Full PDF', 'Paper Metadata', 'Variant Details'])

    with tab1:
        paper = Paper(id=paper_resp.id)
        st.pdf(paper.pdf_raw_path)
        st.download_button(
            label='Download PDF',
            data=open(paper.pdf_raw_path, 'rb').read(),
            icon=':material/download:',
            mime='application/pdf',
            width='stretch',
        )

    with tab2:
        if paper_resp.extraction_status != ExtractionStatus.PARSED:
            st.write('Not yet parsed')
        else:
            paper = Paper(id=paper_resp.id)
            data = json.load(open(paper.metadata_json_path, 'r'))
            md_tab, editable_tab = st.tabs(['View', 'Edit'])
            with md_tab:
                st.markdown(paper_dict_to_markdown(data))
                st.download_button(
                    label='Download JSON',
                    data=json.dumps(data, indent=2),
                    file_name='metadata.json',
                    mime='application/json',
                )
            with editable_tab:
                data['title'] = st.text_input('Title', data['title'])
                data['first_author'] = st.text_input(
                    'First Author', data['first_author']
                )
                data['pub_year'] = st.text_input('Year', data['pub_year'])
                data['journal'] = st.text_input('Journal', data['journal'])
                data['doi'] = st.text_input('DOI', data['doi'])
                data['pmcid'] = st.text_input('PMCID', data['pmcid'])
                data['pmid'] = st.text_input('PMID', data['pmid'])
                data['OA'] = st.checkbox('Open Access', data['OA'])
                data['license'] = st.text_input('License', data['license'])
                data['link'] = st.text_input('Link', data['link'])
                data['abstract'] = st.text_area(
                    'Abstract', data['abstract'], height=200
                )

with left:
    with st.container(horizontal=True, vertical_alignment='center'):
        st.page_link('dashboard.py', label='Curation Dashboard', icon='🏠')
