import pandas as pd
import requests
import streamlit as st

from app.streamlit.api import get_http_error_detail, get_papers, put_paper, FASTAPI_HOST

st.set_page_config(page_title='Papers Dashboard', layout='wide')
left, center, right = st.columns([2, 3, 2])
main = center.container()

with center:
    st.title('📄 PDF Curation')
    st.divider()
    st.subheader('📋 Papers')
    with st.spinner('Loading papers...'):
        try:
            papers = get_papers()
            if not papers:
                st.info('No papers found.')
            else:
                df = pd.DataFrame(papers)
                df['details_url'] = df['id'].apply(
                    lambda paper_id: f'/details?paper_id={paper_id}'
                )
                df['status'] = df['status'].map(
                    {
                        'EXTRACTED': 'Extracted ✅',
                        'QUEUED': 'Queued ⏳',
                        'FAILED': 'Failed ❌',
                    }
                )
                df['thumbnail_path'] = df['thumbnail_path'].map(
                    lambda p: f"{FASTAPI_HOST}{p}"
                )
                st.dataframe(
                    df[['thumbnail_path', 'filename', 'status', 'details_url']],
                    hide_index=True,
                    row_height=100,
                    column_config={
                        'thumbnail_path': st.column_config.ImageColumn(
                            'Thumbnail',
                            help='First page preview',
                            width='small',
                        ),
                        'details_url': st.column_config.LinkColumn(
                            '',
                            display_text='View Extraction Details',
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
