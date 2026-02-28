import json
import time
from typing import Optional

import requests
import streamlit as st
from pydantic import BaseModel, ValidationError

from lib.agents.paper_extraction_agent import (
    PaperExtractionOutput,
)
from lib.evagg.types.base import Paper
from lib.models import ExtractionStatus, PaperResp
from lib.ui.api import (
    delete_paper,
    get_http_error_detail,
    get_paper,
    requeue_paper,
)


class PaperQueryParams(BaseModel):
    paper_id: str
    patient_id: Optional[int] = None
    variant_id: Optional[int] = None

    @classmethod
    def from_query_params(cls) -> 'PaperQueryParams':
        raw_params = {
            'paper_id': st.query_params.get('paper_id'),
            'patient_id': st.query_params.get('patient_id'),
            'variant_id': st.query_params.get('variant_id'),
        }

        if not raw_params['paper_id']:
            st.warning('No paper_id provided in URL.')
            st.stop()

        try:
            return cls(**raw_params)
        except ValidationError:
            # If ints fail to parse, fall back to None instead of crashing
            return cls(
                paper_id=raw_params['paper_id'],
                patient_id=None,
                variant_id=None,
            )


def render_paper_header() -> tuple[
    Paper, PaperResp, PaperExtractionOutput, st.delta_generator.DeltaGenerator
]:
    st.set_page_config(layout='wide')
    paper_query_params = PaperQueryParams.from_query_params()
    with st.spinner('Loading paper...'):
        try:
            paper_resp: PaperResp = get_paper(paper_query_params.paper_id)
            if paper_resp is None:
                st.stop()
        except requests.HTTPError as e:
            st.error(f'Failed to load paper: {get_http_error_detail(e)}')
        except Exception as e:
            st.error(str(e))

    left, center, right = st.columns([1, 10, 1])
    with left:
        with st.container(horizontal=True, vertical_alignment='center'):
            st.page_link('dashboard.py', label='Dashboard', icon='🏠')
    with center:
        if paper_resp.extraction_status != ExtractionStatus.PARSED:
            st.markdown(f'# {paper_resp.filename}')
            st.caption('Not Yet Extracted...')
            st.divider()
            st.stop()
        paper = Paper(id=paper_resp.id)
        with open(paper.metadata_json_path, 'r') as f:
            data = json.load(f)
            paper_extraction_output: PaperExtractionOutput = (
                PaperExtractionOutput.model_validate(data)
            )
        st.markdown(f'# {paper_extraction_output.title}')
        parts = [
            f'{paper_extraction_output.first_author} et al. {paper_extraction_output.publication_year}'
        ]
        if paper_extraction_output.pmid:
            parts.append(f'PMID: {paper_extraction_output.pmid}')
        if paper_extraction_output.journal_name:
            parts.append(paper_extraction_output.journal_name)
        st.caption(' • '.join(parts))
        st.divider()
        left, right = st.columns([4, 2])
        with left:
            with st.container(horizontal=True, vertical_alignment='center'):
                PAPER_PAGES = [
                    ('📄 PDF', 'paper/pdf.py'),
                    ('📝 Paper Metadata', 'paper/metadata.py'),
                    ('👤 Patients', 'paper/patients.py'),
                    ('🧬 Variants', 'paper/variants.py'),
                ]
                for i, (label, page) in enumerate(PAPER_PAGES):
                    if st.button(label, type='tertiary', width='content'):
                        st.query_params['paper_id'] = paper_query_params.paper_id
                        st.switch_page(
                            page, query_params={'paper_id': paper_query_params.paper_id}
                        )
                    if i < len(PAPER_PAGES) - 1:
                        st.space('small')

        with right:
            with st.container(
                horizontal=True,
                vertical_alignment='center',
                horizontal_alignment='center',
            ):
                if paper_resp.extraction_status == ExtractionStatus.PARSED:
                    st.badge(
                        'AI Extraction Success', icon=':material/check:', color='green'
                    )
                elif paper_resp.extraction_status == ExtractionStatus.QUEUED:
                    st.badge('AI Extraction Queued', icon='⏳', color='yellow')
                elif paper_resp.extraction_status == ExtractionStatus.FAILED:
                    st.badge('AI Extraction Failed', icon='❌', color='red')
                if st.button('🔄 Rerun EvAGG', type='tertiary', width='content'):
                    try:
                        requeue_paper(paper_query_params.paper_id)
                        st.toast('EvAGG Job Queued', icon=':material/thumb_up:')
                        st.rerun()
                    except Exception as e:
                        st.toast(f'Failed to requeue: {str(e)}', icon='❌')
                if st.button('🗑️ Delete Paper', type='tertiary', width='content'):
                    try:
                        delete_paper(paper_query_params.paper_id)
                        st.toast('Successfully deleted!', icon='🗑️')
                        st.switch_page('dashboard.py')
                    except Exception as e:
                        st.toast(f'Failed to delete: {str(e)}', icon='❌')

    return paper, paper_resp, paper_extraction_output, center
