import json
import time

import pandas as pd
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
from lib.agents.variant_enrichment_agent import EnrichedVariant, VariantEnrichmentOutput
from lib.agents.variant_extraction_agent import (
    GenomeBuild,
    HgvsInferenceConfidence,
    Variant,
    VariantExtractionOutput,
    VariantType,
)
from lib.agents.variant_harmonization_agent import (
    HarmonizedVariant,
    VariantHarmonizationOutput,
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

            # ----------------------------
            # Load extracted variants
            # ----------------------------
            extracted_data = json.load(open(paper.variants_json_path, 'r'))
            extracted_variants: list[Variant] = VariantExtractionOutput.model_validate(
                extracted_data
            ).variants

            # ----------------------------
            # Load harmonized variants
            # ----------------------------
            harmonized_data = json.load(open(paper.harmonized_variants_json_path, 'r'))
            harmonized_variants: list[HarmonizedVariant] = (
                VariantHarmonizationOutput.model_validate(harmonized_data).variants
            )

            # Enriched variants
            enriched_data = json.load(open(paper.enriched_variants_json_path, 'r'))
            enriched_variants: list[EnrichedVariant] = (
                VariantEnrichmentOutput.model_validate(enriched_data).variants
            )

            for i, harmonized_variant in enumerate(harmonized_variants):
                extracted_variant = extracted_variants[i]
                enriched_variant = enriched_variants[i]

                st.markdown(f'### Variant {i + 1}')

                with st.expander(
                    extracted_variant.variant_description_verbatim
                    or harmonized_variant.hgvs_c
                    or harmonized_variant.hgvs_p
                    or 'Variant'
                ):
                    # ======================================================
                    # Harmonized Variant (PRIMARY DISPLAY)
                    # ======================================================
                    with st.container():
                        st.subheader('Harmonized Variant Info')

                        col1, col2 = st.columns(2)

                        col1.markdown(
                            f'**gnomAD-style coordinates:** '
                            f'{harmonized_variant.gnomad_style_coordinates or "N/A"}'
                        )
                        col1.markdown(f'**rsID:** {harmonized_variant.rsid or "N/A"}')
                        col1.markdown(f'**CAID:** {harmonized_variant.caid or "N/A"}')

                        col2.markdown(
                            f'**HGVS c.:** {harmonized_variant.hgvs_c or "N/A"}'
                        )
                        col2.markdown(
                            f'**HGVS p.:** {harmonized_variant.hgvs_p or "N/A"}'
                        )
                        col2.markdown(
                            f'**HGVS g.:** {harmonized_variant.hgvs_g or "N/A"}'
                        )

                        st.markdown(
                            f'**Harmonization confidence:** '
                            f'{harmonized_variant.normalization_confidence}'
                        )

                        st.text_area(
                            'Harmonization Notes',
                            harmonized_variant.normalization_notes or '',
                            height=140,
                            disabled=True,
                            key=f'{i}-norm-notes',
                        )

                        st.subheader('Variant Type')
                        selected_value = VariantType(
                            st.selectbox(
                                'Variant Type',
                                [vt.value for vt in VariantType],
                                index=[vt.value for vt in VariantType].index(
                                    extracted_variant.variant_type.value
                                )
                                if extracted_variant.variant_type
                                else 0,
                                key=f'{i}-type',
                            )
                        )

                        st.text_area(
                            'Variant Type Evidence Context',
                            extracted_variant.variant_type_evidence_context or '',
                            height=80,
                            disabled=True,
                            key=f'{i}-vtec',
                        )

                    # ======================================================
                    # Extracted Variant Description (READ-ONLY)
                    # ======================================================
                    with st.container():
                        st.subheader('Extracted Variant Context')

                        st.markdown(
                            f'**Variant description (verbatim):** '
                            f'{extracted_variant.variant_description_verbatim or "N/A"}'
                        )

                        st.text_area(
                            'Variant Evidence Context',
                            extracted_variant.variant_evidence_context or '',
                            height=100,
                            disabled=True,
                            key=f'{i}-vec',
                        )

                    #
                    # Annotations
                    #
                    # ======================================================
                    # Annotations (ClinVar + gnomAD + In Silico)
                    # ======================================================
                    with st.container():
                        st.subheader('Annotations')

                        ev = enriched_variant

                        # ----------------------------
                        # ClinVar
                        # ----------------------------
                        st.markdown('#### ClinVar')

                        stars_display = (
                            '⭐' * ev.stars
                            if ev.stars is not None and ev.stars > 0
                            else ('0⭐' if ev.stars == 0 else 'N/A')
                        )

                        clinvar_df = pd.DataFrame(
                            [
                                {
                                    'Pathogenicity': ev.pathogenicity or 'N/A',
                                    'Submissions': ev.submissions or 'N/A',
                                    'Review Status': stars_display,
                                }
                            ]
                        )

                        st.dataframe(
                            clinvar_df, use_container_width=True, hide_index=True
                        )

                        # ----------------------------
                        # In Silico Predictors
                        # ----------------------------
                        st.markdown('#### In Silico Scores')

                        if ev.spliceai:
                            spliceai_display = (
                                f'{ev.spliceai.max_score:.3f}'
                                + (
                                    f' | {ev.spliceai.effect_type}'
                                    if ev.spliceai.effect_type
                                    else ''
                                )
                                + (
                                    f' @ {ev.spliceai.position}'
                                    if ev.spliceai.position is not None
                                    else ''
                                )
                            )
                        else:
                            spliceai_display = 'N/A'

                        in_silico_df = pd.DataFrame(
                            [
                                {
                                    'REVEL': round(ev.revel, 3)
                                    if ev.revel is not None
                                    else 'N/A',
                                    'AlphaMissense Class': ev.alphamissense_class
                                    or 'N/A',
                                    'AlphaMissense Score': round(
                                        ev.alphamissense_score, 3
                                    )
                                    if ev.alphamissense_score is not None
                                    else 'N/A',
                                    'SpliceAI': spliceai_display,
                                    'Exon': ev.exon or 'N/A',
                                }
                            ]
                        )

                        st.dataframe(
                            in_silico_df, use_container_width=True, hide_index=True
                        )

                        # ----------------------------
                        # gnomAD
                        # ----------------------------
                        st.markdown('#### gnomAD')

                        gnomad_df = pd.DataFrame(
                            [
                                {
                                    'Top-level AF': ev.gnomad_top_level_af
                                    if ev.gnomad_top_level_af is not None
                                    else 'N/A',
                                    'Popmax AF': ev.gnomad_popmax_af
                                    if ev.gnomad_popmax_af is not None
                                    else 'N/A',
                                    'Popmax Population': ev.gnomad_popmax_population
                                    or 'N/A',
                                }
                            ]
                        )

                        st.dataframe(
                            gnomad_df, use_container_width=True, hide_index=True
                        )

                    # ======================================================
                    # Downloads
                    # ======================================================
                    col_dl1, col_dl2 = st.columns(2)

                    col_dl1.download_button(
                        label='Download Extracted Variant JSON',
                        data=json.dumps(extracted_data, indent=2),
                        file_name='extracted_variants.json',
                        mime='application/json',
                        key=f'{i}-extract-json',
                    )

                    col_dl2.download_button(
                        label='Download Harmonized Variant JSON',
                        data=json.dumps(harmonized_data, indent=2),
                        file_name='harmonized_variants.json',
                        mime='application/json',
                        key=f'{i}-harm-json',
                    )

with left:
    with st.container(horizontal=True, vertical_alignment='center'):
        st.page_link('dashboard.py', label='Curation Dashboard', icon='🏠')
