import json
import time

import requests
import streamlit as st

from lib.agents.patient_extraction_agent import (
    PatientInfo,
    PatientInfoExtractionOutput,
    RaceEthnicity,
    Sex,
)
from lib.agents.variant_extraction_agent import (
    HgvsInferenceConfidence,
    Inheritance,
    Variant,
    VariantExtractionOutput,
    VariantType,
    Zygosity,
)
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

    tab1, tab2, tab3, tab4 = st.tabs(
        ['Full PDF', 'Paper Metadata', 'Patient Info', 'Variant Details']
    )

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

    with tab3:
        if paper_resp.extraction_status != ExtractionStatus.PARSED:
            st.write('Not yet parsed')
        else:
            paper = Paper(id=paper_resp.id)
            data = json.load(open(paper.patient_info_json_path, 'r'))
            patients: list[PatientInfo] = PatientInfoExtractionOutput.model_validate(
                data
            ).patients
            for i, patient in enumerate(patients):
                with st.expander(f'{patient.identifier or "N/A"}'):
                    # --- Proband Identifier
                    patient.identifier = st.text_input(
                        'Proband Identifier',
                        patient.identifier,
                        key=f'{i}-identifier',
                    )
                    st.text_area(
                        'Proband Identifier Evidence',
                        patient.identifier_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-identifier-evidence',
                    )

                    # --- Sex (enum)
                    patient.sex = Sex(
                        st.selectbox(
                            'Sex',
                            [s.value for s in Sex],
                            index=[s.value for s in Sex].index(patient.sex.value)
                            if patient.sex
                            else 0,
                            key=f'{i}-sex',
                        )
                    )
                    st.text_area(
                        'Sex Evidence',
                        patient.sex_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-sex-evidence',
                    )

                    # --- Age at Diagnosis
                    patient.age_diagnosis = st.text_input(
                        'Age at Diagnosis',
                        patient.age_diagnosis or '',
                        key=f'{i}-age-diagnosis',
                    )
                    st.text_area(
                        'Age at Diagnosis Evidence',
                        patient.age_diagnosis_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-age-diagnosis-evidence',
                    )

                    # --- Age at Report
                    patient.age_report = st.text_input(
                        'Age at Report',
                        patient.age_report or '',
                        key=f'{i}-age-report',
                    )
                    st.text_area(
                        'Age at Report Evidence',
                        patient.age_report_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-age-report-evidence',
                    )

                    # --- Age at Death
                    patient.age_death = st.text_input(
                        'Age at Death',
                        patient.age_death or '',
                        key=f'{i}-age-death',
                    )
                    st.text_area(
                        'Age at Death Evidence',
                        patient.age_death_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-age-death-evidence',
                    )

                    # --- Country of Origin
                    patient.country_of_origin = st.text_input(
                        'Country of Origin',
                        patient.country_of_origin or '',
                        key=f'{i}-country',
                    )
                    st.text_area(
                        'Country of Origin Evidence',
                        patient.country_of_origin_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-country-evidence',
                    )

                    # --- Race/Ethnicity (enum)
                    patient.race_ethnicity = RaceEthnicity(
                        st.selectbox(
                            'Race/Ethnicity',
                            [r.value for r in RaceEthnicity],
                            index=[r.value for r in RaceEthnicity].index(
                                patient.race_ethnicity.value
                            )
                            if patient.race_ethnicity
                            else 0,
                            key=f'{i}-race',
                        )
                    )
                    st.text_area(
                        'Race/Ethnicity Evidence',
                        patient.race_ethnicity_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-race-evidence',
                    )

    with tab4:
        if paper_resp.extraction_status != ExtractionStatus.PARSED:
            st.write('Not yet parsed')
        else:
            paper = Paper(id=paper_resp.id)
            data = json.load(open(paper.variants_json_path, 'r'))
            variants: list[Variant] = VariantExtractionOutput.model_validate(
                data
            ).variants
            for i, variant in enumerate(variants):
                st.markdown(f'### Variant {i + 1} ')
                with st.expander(f'{variant.variant_verbatim or "New variant"}'):
                    with st.container():
                        st.subheader('Variant Summary')
                        col1, col2, col3_label, col3_input = st.columns([1, 3, 1, 3])
                        col1.markdown(f'**Gene:** {variant.gene or "N/A"}')
                        col2.markdown(
                            f'**Variant:** {variant.variant_verbatim or "N/A"}'
                        )
                        col3_label.markdown('**Transcript:**')
                        variant.transcript = col3_input.text_input(
                            'Transcript',
                            variant.transcript or '',
                            key=f'{i}-transcript',
                            label_visibility='collapsed',
                        )
                        st.text_area(
                            'Variant Evidence Context',
                            variant.variant_evidence_context or '',
                            height=60,
                            disabled=True,
                            key=f'{i}-vec',
                        )

                        variant.genomic_coordinates = st.text_input(
                            'Genomic Coordinates',
                            variant.genomic_coordinates or '',
                            key=f'{i}-coords',
                        )
                        variant.hgvs_c = st.text_input(
                            'HGVS c.', variant.hgvs_c or '', key=f'{i}-hgvs_c'
                        )
                        variant.hgvs_p = st.text_input(
                            'HGVS p.', variant.hgvs_p or '', key=f'{i}-hgvs_p'
                        )

                    # --- HGVS Inference (info only) ---
                    with st.expander('HGVS Inference (info only)', expanded=False):
                        st.text(f'HGVS c. inferred: {variant.hgvs_c_inferred or ""}')
                        st.text(f'HGVS p. inferred: {variant.hgvs_p_inferred or ""}')
                        st.text(
                            f'HGVS Inference Confidence: {variant.hgvs_inference_confidence.value if variant.hgvs_inference_confidence else ""}'
                        )
                        st.text_area(
                            'HGVS Inference Evidence',
                            variant.hgvs_inference_evidence_context or '',
                            height=60,
                            disabled=True,
                            key=f'{i}-hic',
                        )

                    with st.container():
                        st.subheader('Variant Type')
                        selected_value = VariantType(
                            st.selectbox(
                                'Variant Type',
                                [vt.value for vt in VariantType],  # display strings
                                index=[vt.value for vt in VariantType].index(
                                    variant.variant_type.value
                                )
                                if variant.variant_type
                                else 0,
                                key=f'{i}-type',
                            )
                        )
                        st.text_area(
                            'Variant Type Evidence Context',
                            variant.variant_type_evidence_context or '',
                            height=60,
                            disabled=True,
                            key=f'{i}-vtec',
                        )

                    with st.container():
                        st.subheader('Zygosity')
                        variant.zygosity = Zygosity(
                            st.selectbox(
                                'Zygosity',
                                [z.value for z in Zygosity],  # display strings
                                index=[x.value for x in Zygosity].index(
                                    variant.zygosity.value
                                )
                                if variant.zygosity
                                else 0,
                                key=f'{i}-zygosity',
                            )
                        )
                        st.text_area(
                            'Zygosity Evidence Context',
                            variant.zygosity_evidence_context or '',
                            height=60,
                            disabled=True,
                            key=f'{i}-zec',
                        )

                    with st.container():
                        st.subheader('Inheritance')
                        variant.inheritance = Inheritance(
                            st.selectbox(
                                'Inheritance',
                                [inh.value for inh in Inheritance],  # display strings
                                index=[inh.value for inh in Inheritance].index(
                                    variant.inheritance.value
                                )
                                if variant.inheritance
                                else 0,
                                key=f'{i}-inheritance',
                            )
                        )
                        st.text_area(
                            'Inheritance Evidence Context',
                            variant.inheritance_evidence_context or '',
                            height=60,
                            disabled=True,
                            key=f'{i}-iec',
                        )

with left:
    with st.container(horizontal=True, vertical_alignment='center'):
        st.page_link('dashboard.py', label='Curation Dashboard', icon='🏠')
