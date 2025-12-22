import pandas as pd
import requests
import streamlit as st

from app.streamlit.api import FASTAPI_HOST, get_http_error_detail, get_papers, put_paper

st.set_page_config(page_title='Papers Dashboard', layout='wide')
left, center, right = st.columns([2, 3, 2])
main = center.container()

with center:
    st.title('📄 Curation Dashboard')
    st.divider()
    st.subheader('📋 Papers')
    with st.spinner('Loading papers...'):
        try:
            papers = get_papers()
            if not papers:
                st.info('No papers found.')
            else:
                df = pd.DataFrame(papers)
                status_map = {
                    'EXTRACTED': 'Extracted ✅',
                    'QUEUED': 'Queued ⏳',
                    'FAILED': 'Failed ❌',
                }
                df['status'] = df.apply(
                    lambda row: f"/details?paper_id={row['id']}#{status_map.get(row['status'], row['status'])}",
                    axis=1,
                )
                df['thumbnail_path'] = df['thumbnail_path'].map(
                    lambda p: f'{FASTAPI_HOST}{p}'
                )
                df['rerun'] = '🔄 Rerun EvAGG'
                st.dataframe(
                    df[['thumbnail_path', 'filename', 'status', 'rerun']],
                    row_height=100,
                    column_config={
                        'thumbnail_path': st.column_config.ImageColumn(
                            'Thumbnail',
                            help='First page preview',
                        ),
                        'status': st.column_config.LinkColumn(
                            'Status',
                            # Regex to extract text after the '#'
                            # Note, this is a major hack to get around the lack of a better way of doing this.
                            display_text=r".*?#(.+)$"
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
