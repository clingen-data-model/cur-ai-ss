import time

import pandas as pd
import requests
import streamlit as st

from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env
from lib.models import ExtractionStatus, PaperResp
from lib.ui.api import get_http_error_detail, get_papers, put_paper

st.set_page_config(page_title='Papers Dashboard', layout='wide')
left, center, right = st.columns([2, 3, 2])
main = center.container()

QUEUED_EXTRACTION_TEXT = 'Pending Extraction...'

with center:
    st.title('📄 Dashboard')
    st.divider()
    st.subheader('📋 Papers')
    with st.spinner('Loading papers...'):
        try:
            paper_resps = get_papers()
            if not paper_resps:
                st.info('No papers found.')
            else:
                papers_by_id = {
                    p.id: Paper(id=p.id).with_metadata() for p in paper_resps
                }
                df = pd.DataFrame([p.model_dump() for p in paper_resps])
                df['thumbnail_path'] = df['id'].map(
                    lambda paper_id: f'http://{env.API_HOSTNAME}:{env.API_PORT}{papers_by_id[paper_id].pdf_thumbnail_path}'  # note the leading slash
                )
                df['title'] = df.apply(
                    lambda row: f'/details?paper_id={row["id"]}#{papers_by_id[row["id"]].title or QUEUED_EXTRACTION_TEXT}',
                    axis=1,
                )
                df['first_author'] = df.apply(
                    lambda row: f'/details?paper_id={row["id"]}#{papers_by_id[row["id"]].first_author or QUEUED_EXTRACTION_TEXT}',
                    axis=1,
                )
                status_map = {
                    'EXTRACTED': 'Extracted ✅',
                    'QUEUED': 'Queued ⏳',
                    'FAILED': 'Failed ❌',
                }
                df['extraction_status'] = df.apply(
                    lambda row: f'/details?paper_id={row["id"]}#{status_map.get(row["extraction_status"], row["extraction_status"])}',
                    axis=1,
                )
                st.dataframe(
                    df[
                        [
                            'thumbnail_path',
                            'title',
                            'first_author',
                            'filename',
                            'extraction_status',
                        ]
                    ],
                    row_height=100,
                    column_config={
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
                        'extraction_status': st.column_config.LinkColumn(
                            'Extraction Status',
                            # Regex to extract text after the '#'
                            # Note, this is a major hack to get around the lack of a better way of doing this.
                            display_text=r'.*?#(.+)$',
                        ),
                    },
                )
        except requests.HTTPError as e:
            st.error(f'Failed to load papers: {get_http_error_detail(e)}')
        except Exception as e:
            st.error(str(e))
    st.subheader('➕ Add New Paper')
    uploaded_file = st.file_uploader(
        'Upload a PDF',
        type=['pdf'],
        accept_multiple_files=False,
    )
    if uploaded_file is not None:
        if st.button('Submit Paper'):
            with st.spinner('Uploading PDF...'):
                try:
                    result = put_paper(uploaded_file)
                    st.success('Paper submitted successfully')
                    time.sleep(0.5)
                    st.rerun()
                except requests.HTTPError as e:
                    st.error(f'Upload failed: {e}, {get_http_error_detail(e)}')
                except Exception as e:
                    st.error(str(e))
