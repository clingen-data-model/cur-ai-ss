import json
import time

import requests
import streamlit as st

from lib.agents.paper_extraction_agent import (
    PaperExtractionOutput,
    PaperType,
    TestingMethod,
)
from lib.agents.patient_extraction_agent import (
    CountryCode,
    PatientInfo,
    PatientInfoExtractionOutput,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)
from lib.agents.variant_extraction_agent import (
    GenomeBuild,
    HgvsInferenceConfidence,
    Variant,
    VariantExtractionOutput,
    VariantType,
)
from lib.evagg.types.base import Paper
from lib.models import ExtractionStatus, PaperResp
from lib.ui.api import (
    delete_paper,
    get_http_error_detail,
    get_paper,
    requeue_paper,
)
from lib.ui.helpers import paper_extraction_output_to_markdown


@st.fragment
def render_editable_paper_extraction_tab(
    paper_extraction_output: PaperExtractionOutput,
) -> None:
    paper_extraction_output.title = st.text_input(
        'Title', paper_extraction_output.title
    )

    paper_extraction_output.first_author = st.text_input(
        'First Author', paper_extraction_output.first_author
    )

    # Publication Year
    pub_year_input = st.text_input(
        'Publication Year',
        str(paper_extraction_output.publication_year)
        if paper_extraction_output.publication_year
        else '',
    )
    paper_extraction_output.publication_year = (
        int(pub_year_input) if pub_year_input.isdigit() else None
    )

    paper_extraction_output.journal_name = st.text_input(
        'Journal Name', paper_extraction_output.journal_name
    )

    paper_extraction_output.paper_types = [
        PaperType(pt)
        for pt in st.pills(
            'Paper Types',
            options=[pt.value for pt in PaperType],
            selection_mode='multi',
            default=[pt.value for pt in paper_extraction_output.paper_types]
            if paper_extraction_output.paper_types
            else [],
            key='paper-types',
        )
    ]

    paper_extraction_output.abstract = st.text_area(
        'Abstract', paper_extraction_output.abstract, height=200
    )

    # Testing methods
    for i in range(len(paper_extraction_output.testing_methods)):
        paper_extraction_output.testing_methods[i] = TestingMethod(
            st.selectbox(
                f'Testing Method #{i + 1}',
                [tm.value for tm in TestingMethod],
                index=[tm.value for tm in TestingMethod].index(
                    paper_extraction_output.testing_methods[i].value
                )
                if paper_extraction_output.testing_methods[i]
                else 0,
                key=f'{i}-testing-method',
            )
        )

        paper_extraction_output.testing_methods_evidence[i] = st.text_area(
            f'Testing Method #{i + 1} Evidence',
            paper_extraction_output.testing_methods_evidence[i] or '',
            height=150,
            key=f'{i}-testing-evidence',
        )


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
            paper_extraction_output: PaperExtractionOutput = (
                PaperExtractionOutput.model_validate(data)
            )
            md_tab, editable_tab = st.tabs(['View', 'Edit'])
            with md_tab:
                st.markdown(
                    paper_extraction_output_to_markdown(paper_extraction_output)
                )
                st.download_button(
                    label='Download JSON',
                    data=json.dumps(data, indent=2),
                    file_name='metadata.json',
                    mime='application/json',
                )
            with editable_tab:
                render_editable_paper_extraction_tab(paper_extraction_output)

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
                    # --- Patient Identifier
                    patient.identifier = st.text_input(
                        'Patient Identifier',
                        patient.identifier,
                        key=f'{i}-identifier',
                    )
                    st.text_area(
                        'Patient Identifier Evidence',
                        patient.identifier_evidence or '',
                        height=60,
                        disabled=True,
                        key=f'{i}-identifier-evidence',
                    )

                    # --- ProbandStatus (enum)
                    patient.proband_status = ProbandStatus(
                        st.selectbox(
                            'Proband Status',
                            [ps.value for ps in ProbandStatus],
                            index=[ps.value for ps in ProbandStatus].index(
                                patient.proband_status.value
                            )
                            if patient.proband_status
                            else 0,
                            key=f'{i}-proband-status',
                        )
                    )

                    # --- SexAtBirth (enum)
                    patient.sex = SexAtBirth(
                        st.selectbox(
                            'Sex At Birth',
                            [s.value for s in SexAtBirth],
                            index=[s.value for s in SexAtBirth].index(patient.sex.value)
                            if patient.sex
                            else 0,
                            key=f'{i}-sex',
                        )
                    )
                    st.text_area(
                        'Sex At Birth Evidence',
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
                    patient.country_of_origin = CountryCode(
                        st.selectbox(
                            'Country of Origin',
                            [c.value for c in CountryCode],
                            index=[c.value for c in CountryCode].index(
                                patient.country_of_origin.value
                            )
                            if patient.country_of_origin
                            else 0,
                            key=f'{i}-country',
                        )
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
                st.markdown(f'### Variant {i + 1}')
                with st.expander(
                    f'{variant.variant_description_verbatim or "New variant"}'
                ):
                    with st.container():
                        st.subheader('Variant Summary')
                        col1, col2, col3_label, col3_input = st.columns([1, 3, 1, 3])
                        col1.markdown(f'**Gene:** {variant.gene or "N/A"}')
                        col2.markdown(
                            f'**Variant:** {variant.variant_description_verbatim or "N/A"}'
                        )

                        col3_label.markdown('**Transcript:**')
                        variant.transcript = col3_input.text_input(
                            'Transcript',
                            variant.transcript or '',
                            key=f'{i}-transcript',
                            label_visibility='collapsed',
                        )

                        col3_label.markdown('**Protein Accession:**')
                        variant.protein_accession = col3_input.text_input(
                            'Protein Accession',
                            variant.protein_accession or '',
                            key=f'{i}-protein',
                            label_visibility='collapsed',
                        )

                        col3_label.markdown('**Genomic Accession:**')
                        variant.genomic_accession = col3_input.text_input(
                            'Genomic Accession',
                            variant.genomic_accession or '',
                            key=f'{i}-genomic',
                            label_visibility='collapsed',
                        )

                        col3_label.markdown('**LRG Accession:**')
                        variant.lrg_accession = col3_input.text_input(
                            'LRG Accession',
                            variant.lrg_accession or '',
                            key=f'{i}-lrg',
                            label_visibility='collapsed',
                        )

                        col3_label.markdown('**Gene Accession:**')
                        variant.gene_accession = col3_input.text_input(
                            'Gene Accession',
                            variant.gene_accession or '',
                            key=f'{i}-gene-acc',
                            label_visibility='collapsed',
                        )

                        variant.genomic_coordinates = st.text_input(
                            'Genomic Coordinates',
                            variant.genomic_coordinates or '',
                            key=f'{i}-coords',
                        )

                        options = [''] + [gb.value for gb in GenomeBuild]
                        index = (
                            options.index(variant.genome_build.value)
                            if variant.genome_build
                            else 0
                        )
                        selected = st.selectbox(
                            'Genome Build', options, index=index, key=f'{i}-build'
                        )
                        variant.genome_build = (
                            GenomeBuild(selected) if selected else None
                        )

                        variant.rsid = st.text_input(
                            'rsID', variant.rsid or '', key=f'{i}-rsid'
                        )
                        variant.caid = st.text_input(
                            'CAID', variant.caid or '', key=f'{i}-caid'
                        )

                        variant.hgvs_c = st.text_input(
                            'HGVS c.', variant.hgvs_c or '', key=f'{i}-hgvs_c'
                        )
                        variant.hgvs_p = st.text_input(
                            'HGVS p.', variant.hgvs_p or '', key=f'{i}-hgvs_p'
                        )
                        variant.hgvs_g = st.text_input(
                            'HGVS g.', variant.hgvs_g or '', key=f'{i}-hgvs_g'
                        )

                    # --- HGVS Inference (info only) ---
                    with st.expander('HGVS Inference (info only)', expanded=False):
                        st.text(f'HGVS c. inferred: {variant.hgvs_c_inferred or ""}')
                        st.text(f'HGVS p. inferred: {variant.hgvs_p_inferred or ""}')
                        st.text(
                            f'HGVS c. inference confidence: {variant.hgvs_c_inference_confidence.value if variant.hgvs_c_inference_confidence else ""}'
                        )
                        st.text(
                            f'HGVS p. inference confidence: {variant.hgvs_p_inference_confidence.value if variant.hgvs_p_inference_confidence else ""}'
                        )
                        st.text_area(
                            'HGVS c. inference evidence',
                            variant.hgvs_c_inference_evidence_context or '',
                            height=60,
                            disabled=True,
                            key=f'{i}-hic_c',
                        )
                        st.text_area(
                            'HGVS p. inference evidence',
                            variant.hgvs_p_inference_evidence_context or '',
                            height=60,
                            disabled=True,
                            key=f'{i}-hic_p',
                        )

                    with st.container():
                        st.subheader('Variant Type')
                        selected_value = VariantType(
                            st.selectbox(
                                'Variant Type',
                                [vt.value for vt in VariantType],
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

with left:
    with st.container(horizontal=True, vertical_alignment='center'):
        st.page_link('dashboard.py', label='Curation Dashboard', icon='🏠')
