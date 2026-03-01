import time

import pandas as pd
import requests
import streamlit as st

from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env
from lib.models import PaperResp, PipelineStatus
from lib.ui.api import (
    delete_paper,
    get_genes,
    get_http_error_detail,
    get_papers,
    put_paper,
)

st.set_page_config(page_title='Papers Dashboard', layout='wide')
left, center, right = st.columns([2, 5, 2])
main = center.container()

CURATIONS_DF_KEY = 'CURATIONS_DF_KEY'
QUEUED_EXTRACTION_TEXT = 'Pending Extraction...'

# Global Requests
gene_resps = get_genes()
if not gene_resps:
    st.error('No genes found, cannot proceed.')
    st.stop()  # stop further execution


def papers_df_on_change() -> None:
    # deleted_rows returns the
    deleted_idxs = st.session_state[CURATIONS_DF_KEY]['deleted_rows']
    for deleted_idx in reversed(
        sorted(deleted_idxs)
    ):  # iterate in reversed order as paper_resps will be mutated!
        if paper_resps and 0 <= deleted_idx < len(paper_resps):
            paper_id = paper_resps[deleted_idx].id
            delete_paper(paper_id)
            paper_resps.pop(deleted_idx)


@st.dialog('Upload PDF and Select Gene')
def upload_paper_modal() -> None:
    with st.form('paper'):
        uploaded_file = st.file_uploader(
            'Upload a PDF',
            type=['pdf'],
            accept_multiple_files=False,
        )
        gene_symbol = st.selectbox(
            'Select gene',
            options=[gene_resp.symbol for gene_resp in gene_resps],
            placeholder='Gene Symbol',
            index=None,
        )
        submitted = st.form_submit_button('Submit')
        if submitted:
            if not uploaded_file or not gene_symbol:
                st.error('Both an uploaded PDF and a selected gene are required')
                return
            with st.spinner('Uploading PDF...'):
                try:
                    result = put_paper(uploaded_file, gene_symbol)
                    st.success('Paper submitted successfully')
                    time.sleep(0.5)
                    st.rerun()
                except requests.HTTPError as e:
                    st.error(f'Upload failed: {e}, {get_http_error_detail(e)}')
                except Exception as e:
                    st.error(str(e))


def render_papers_df(papers_resps: list[PaperResp]) -> None:
    papers_by_id = {p.id: Paper(id=p.id).with_metadata() for p in paper_resps}
    df = pd.DataFrame([p.model_dump() for p in paper_resps])
    df['thumbnail_path'] = df['id'].map(
        lambda paper_id: f'{env.PROTOCOL}{env.API_ENDPOINT}{papers_by_id[paper_id].pdf_thumbnail_path}'  # note the leading slash
    )
    df['title'] = df.apply(
        lambda row: f'/paper-pdf?paper_id={row["id"]}#{papers_by_id[row["id"]].title or QUEUED_EXTRACTION_TEXT}',
        axis=1,
    )
    df['first_author'] = df.apply(
        lambda row: f'/paper-pdf?paper_id={row["id"]}#{papers_by_id[row["id"]].first_author or QUEUED_EXTRACTION_TEXT}',
        axis=1,
    )
    df['pipeline_status'] = df.apply(
        lambda row: f'/paper-pdf?paper_id={row["id"]}#{PipelineStatus(row["pipeline_status"]).icon}',
        axis=1,
    )
    st.data_editor(
        df[
            [
                'gene_symbol',
                'thumbnail_path',
                'title',
                'first_author',
                'filename',
                'pipeline_status',
            ]
        ],
        row_height=100,
        column_config={
            'gene_symbol': st.column_config.Column('Gene Symbol'),
            'thumbnail_path': st.column_config.ImageColumn(
                'Thumbnail',
                help='First page preview',
            ),
            'title': st.column_config.LinkColumn(
                'Title',
                # Regex to extract text after the '#'
                # Note, this is a major hack to get around the lack of a better way of doing this.
                display_text=r'.*?#(.+)$',
            ),
            'first_author': st.column_config.LinkColumn(
                'First Author',
                # Regex to extract text after the '#'
                # Note, this is a major hack to get around the lack of a better way of doing this.
                display_text=r'.*?#(.+)$',
            ),
            'filename': st.column_config.Column('Filename'),
            'pipeline_status': st.column_config.LinkColumn(
                'Extraction Status',
                # Regex to extract text after the '#'
                # Note, this is a major hack to get around the lack of a better way of doing this.
                display_text=r'.*?#(.+)$',
            ),
        },
        disabled=[
            'gene_symbol',
            'thumbnail_path',
            'title',
            'first_author',
            'filename',
            'pipeline_status',
        ],
        num_rows='delete',
        key=CURATIONS_DF_KEY,
        on_change=papers_df_on_change,
    )


with center:
    st.title('📄 Curation AI Assistant Dashboard')
    st.divider()
    st.subheader('📋 Curations')
    with st.spinner('Loading curations...'):
        try:
            paper_resps = get_papers()
            if paper_resps:
                render_papers_df(paper_resps)
            else:
                st.info('No papers found.')
        except requests.HTTPError as e:
            st.error(f'Failed to load papers: {get_http_error_detail(e)}')
        except Exception as e:
            st.error(str(e))

    # Button that triggers the modal
    if st.button('➕ Add New Curation', width='stretch'):
        upload_paper_modal()
