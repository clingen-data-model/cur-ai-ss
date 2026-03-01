import json
from collections import defaultdict

import streamlit as st

from lib.agents.patient_extraction_agent import (
    CountryCode,
    PatientInfo,
    PatientInfoExtractionOutput,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)
from lib.agents.patient_variant_linking_agent import (
    PatientVariantLink,
    PatientVariantLinkerOutput,
)
from lib.agents.variant_extraction_agent import Variant, VariantExtractionOutput
from lib.agents.variant_harmonization_agent import (
    HarmonizedVariant,
    VariantHarmonizationOutput,
)
from lib.ui.paper.header import PaperQueryParams, render_paper_header
from lib.models import PipelineStatus


def render_patient(
    patient: PatientInfo,
    patient_links: list[tuple[PatientVariantLink, Variant, HarmonizedVariant]],
    expanded: bool,
    key_prefix: str,
) -> None:
    with st.expander(
        f'{patient.identifier or "N/A"}',
        expanded=expanded,
    ):
        # --- Patient Identifier
        patient.identifier = st.text_input(
            'Patient Identifier',
            patient.identifier,
            key=f'{key_prefix}-identifier',
        )

        st.text_area(
            'Patient Identifier Evidence',
            patient.identifier_evidence or '',
            height=60,
            disabled=True,
            key=f'{key_prefix}-identifier-evidence',
        )

        # --- Proband Status
        patient.proband_status = ProbandStatus(
            st.selectbox(
                'Proband Status',
                [ps.value for ps in ProbandStatus],
                index=(
                    [ps.value for ps in ProbandStatus].index(
                        patient.proband_status.value
                    )
                    if patient.proband_status
                    else 0
                ),
                key=f'{key_prefix}-proband-status',
            )
        )

        # --- Sex At Birth
        patient.sex = SexAtBirth(
            st.selectbox(
                'Sex At Birth',
                [s.value for s in SexAtBirth],
                index=(
                    [s.value for s in SexAtBirth].index(patient.sex.value)
                    if patient.sex
                    else 0
                ),
                key=f'{key_prefix}-sex',
            )
        )

        st.text_area(
            'Sex At Birth Evidence',
            patient.sex_evidence or '',
            height=60,
            disabled=True,
            key=f'{key_prefix}-sex-evidence',
        )

        # --- Ages
        col1, col2, col3 = st.columns(3)

        with col1:
            patient.age_diagnosis = st.text_input(
                'Age at Diagnosis',
                patient.age_diagnosis or '',
                key=f'{key_prefix}-age-diagnosis',
            )
            st.text_area(
                'Age at Diagnosis Evidence',
                patient.age_diagnosis_evidence or '',
                height=60,
                disabled=True,
                key=f'{key_prefix}-age-diagnosis-evidence',
            )

        with col2:
            patient.age_report = st.text_input(
                'Age at Report',
                patient.age_report or '',
                key=f'{key_prefix}-age-report',
            )
            st.text_area(
                'Age at Report Evidence',
                patient.age_report_evidence or '',
                height=60,
                disabled=True,
                key=f'{key_prefix}-age-report-evidence',
            )

        with col3:
            patient.age_death = st.text_input(
                'Age at Death',
                patient.age_death or '',
                key=f'{key_prefix}-age-death',
            )
            st.text_area(
                'Age at Death Evidence',
                patient.age_death_evidence or '',
                height=60,
                disabled=True,
                key=f'{key_prefix}-age-death-evidence',
            )

        # --- Country + Ethnicity
        col1, col2 = st.columns(2)

        with col1:
            patient.country_of_origin = CountryCode(
                st.selectbox(
                    'Country of Origin',
                    [c.value for c in CountryCode],
                    index=(
                        [c.value for c in CountryCode].index(
                            patient.country_of_origin.value
                        )
                        if patient.country_of_origin
                        else 0
                    ),
                    key=f'{key_prefix}-country',
                )
            )

            st.text_area(
                'Country of Origin Evidence',
                patient.country_of_origin_evidence or '',
                height=60,
                disabled=True,
                key=f'{key_prefix}-country-evidence',
            )

        with col2:
            patient.race_ethnicity = RaceEthnicity(
                st.selectbox(
                    'Race/Ethnicity',
                    [r.value for r in RaceEthnicity],
                    index=(
                        [r.value for r in RaceEthnicity].index(
                            patient.race_ethnicity.value
                        )
                        if patient.race_ethnicity
                        else 0
                    ),
                    key=f'{key_prefix}-race',
                )
            )

            st.text_area(
                'Race/Ethnicity Evidence',
                patient.race_ethnicity_evidence or '',
                height=60,
                disabled=True,
                key=f'{key_prefix}-race-evidence',
            )

        variant_count = len(patient_links)
        if variant_count == 0:
            st.caption('No linked variants', text_alignment='center')
            return
        with st.popover(f'Variants ({variant_count})', width='stretch'):
            for i, (link, variant, harmonized_variant) in enumerate(patient_links):
                title = (
                    variant.variant_description_verbatim
                    or harmonized_variant.hgvs_c
                    or harmonized_variant.hgvs_p
                    or f'Variant {link.variant_id}'
                )
                st.page_link(
                    'paper/variants.py',  # adjust path to your actual variants page
                    label=title,
                    query_params={  # type: ignore
                        'paper_id': paper_query_params.paper_id,
                        'variant_id': link.variant_id,
                    },
                )
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(
                        f'**Zygosity:** {link.zygosity.value}  \n'
                        f'**Inheritance:** {link.inheritance.value}  \n'
                        f'**Link Type:** {link.link_type.value}'
                    )

                with col2:
                    testing = (
                        f'  \n**Testing:** {", ".join(m.value for m in link.testing_methods)}'
                        if link.testing_methods
                        else ''
                    )
                    st.markdown(f'**Confidence:** {link.confidence}{testing}')

                if link.evidence_context:
                    st.markdown(f'**Evidence:** {link.evidence_context}')

                if link.testing_methods_evidence:
                    st.markdown(
                        f'**Testing Evidence:** '
                        f'{", ".join(link.testing_methods_evidence)}'
                    )

                if link.linkage_notes:
                    with st.expander('Notes', expanded=False):
                        st.write(link.linkage_notes)

                # subtle separator between variants (not after last)
                if i < len(patient_links) - 1:
                    st.markdown('---')


paper_query_params = PaperQueryParams.from_query_params()
paper, paper_resp, paper_extraction_output, center = render_paper_header()
with center:
    if not paper_extraction_output:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()
    if paper_resp.pipeline_status != PipelineStatus.COMPLETED:
        st.write(f'Entity Linking not yet completed...')
        st.stop()
    # -----------------------------
    # Load patients & variants & links
    # -----------------------------
    with open(paper.patient_info_json_path, 'r') as f:
        patient_info_data = json.load(f)
    patients: list[PatientInfo] = PatientInfoExtractionOutput.model_validate(
        patient_info_data
    ).patients
    with open(paper.variants_json_path, 'r') as f:
        extracted_data = json.load(f)
        extracted_variants: list[Variant] = VariantExtractionOutput.model_validate(
            extracted_data
        ).variants
    with open(paper.harmonized_variants_json_path, 'r') as f:
        harmonized_variant_data = json.load(f)
        harmonized_variants: list[HarmonizedVariant] = (
            VariantHarmonizationOutput.model_validate(harmonized_variant_data).variants
        )
    with open(paper.patient_variant_links_json_path, 'r') as f:
        link_data = json.load(f)
    links: list[PatientVariantLink] = PatientVariantLinkerOutput.model_validate(
        link_data
    ).links
    links_by_patient: dict[
        int, list[tuple[PatientVariantLink, Variant, HarmonizedVariant]]
    ] = defaultdict(list)
    for link in links:
        links_by_patient[link.patient_id].append(
            (
                link,
                extracted_variants[link.variant_id - 1],
                harmonized_variants[link.variant_id - 1],
            )
        )

    # -----------------------------
    # Display Patients
    # -----------------------------
    indexed_patients = list(enumerate(patients, start=1))
    probands = [
        (i, p) for i, p in indexed_patients if p.proband_status == ProbandStatus.Proband
    ]
    non_probands = [
        (i, p) for i, p in indexed_patients if p.proband_status != ProbandStatus.Proband
    ]
    tabs = [
        f'Probands ({len(probands)})',
        f'Non-Probands ({len(non_probands)})',
    ]
    proband_tab, non_proband_tab = st.tabs(
        tabs,
        default=tabs[1]
        if paper_query_params.patient_id in {p[0] for p in non_probands}
        else tabs[0],
    )
    with proband_tab:
        if not probands:
            st.info('No probands detected.')
        for original_idx, patient in probands:
            st.markdown(f'### Patient {original_idx}')
            render_patient(
                patient,
                patient_links=links_by_patient.get(original_idx, []),
                expanded=(paper_query_params.patient_id == original_idx),
                key_prefix=f'patient-{original_idx}',
            )
    with non_proband_tab:
        if not non_probands:
            st.info('No non-probands detected.')
        for original_idx, patient in non_probands:
            st.markdown(f'### Patient {original_idx}')
            render_patient(
                patient,
                patient_links=links_by_patient.get(original_idx, []),
                expanded=(paper_query_params.patient_id == original_idx),
                key_prefix=f'patient-{original_idx}',
            )
