import pandas as pd
import requests
import streamlit as st

from app.models import ExtractionStatus, PaperResp
from app.streamlit.api import FASTAPI_HOST, get_http_error_detail, get_papers, put_paper
from lib.evagg.types.base import Paper

st.set_page_config(page_title='Papers Dashboard', layout='wide')
left, center, right = st.columns([2, 3, 2])
main = center.container()

QUEUED_EXTRACTION_TEXT = 'Pending Extraction...'

with center:
    st.title('📄 Curation Dashboard')
    st.divider()
    st.subheader('📋 Papers')
    with st.spinner('Loading papers...'):
        try:
            paper_resps = get_papers()
            if not paper_resps:
                st.info('No papers found.')
            else:
                papers_by_id = {
                    p.id: Paper(id=p.id).with_metadata()
                    for p in paper_resps
                }
                df = pd.DataFrame([p.model_dump() for p in paper_resps])
                df['thumbnail_path'] = df['id'].map(
                    lambda paper_id: f'{FASTAPI_HOST}{papers_by_id[paper_id].pdf_thumbnail_path}'
                )
                df['title'] = df['id'].map(
                    lambda paper_id: papers_by_id[paper_id].title
                    or QUEUED_EXTRACTION_TEXT
                )
                df['first_author'] = df['id'].map(
                    lambda paper_id: papers_by_id[paper_id].first_author
                    or QUEUED_EXTRACTION_TEXT
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
                    st.json(result)
                    st.rerun()
                except requests.HTTPError as e:
                    st.error(f'Upload failed: {e}, {get_http_error_detail(e)}')
                except Exception as e:
                    st.error(str(e))
