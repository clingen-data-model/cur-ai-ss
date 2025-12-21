import pandas as pd
import requests
import streamlit as st

from app.streamlit.api import get_papers, put_paper

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
                st.dataframe(
                    df[['file_name', 'status', 'details_url']],
                    hide_index=True,
                    column_config={
                        'details_url': st.column_config.LinkColumn(
                            '',
                            display_text='View Extraction Details',
                        )
                    },
                )
        except requests.HTTPError as e:
            st.error(f'Failed to load papers: {e}')
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
                    st.error(f'Upload failed: {e}')
                except Exception as e:
                    st.error(str(e))
