import json

import pandas as pd
import streamlit as st

from lib.agents.patient_variant_linking_agent import (
    EvidenceBlock,
    Inheritance,
    PatientVariantLink,
    PatientVariantLinkerOutput,
    TestingMethod,
    Zygosity,
)
from lib.models import ExtractedVariantResp, PaperResp, PatientResp, PipelineStatus
from lib.models.patient import (
    Patient,
    PatientExtractionOutput,
)
from lib.models.variant import HarmonizedVariant, VariantHarmonizationOutput
from lib.ui.api import get_patients, get_variants
from lib.ui.paper.shared import (
    get_gnomad_url,
    render_highlight_controls,
)


def _render_evidence_block(
    evidence_block: EvidenceBlock, paper_id: str, block_id: str
) -> None:
    """Render an EvidenceBlock with reasoning and evidence sources."""
    st.text_area('Reasoning', evidence_block.reasoning, height=20, disabled=True)

    # Display evidence sources
    evidence_sources = []
    if evidence_block.quote:
        evidence_sources.append(('Text Evidence', evidence_block.quote))
    if evidence_block.table_id is not None:
        evidence_sources.append(('Table', f'Table #{evidence_block.table_id}'))
    if evidence_block.image_id is not None:
        evidence_sources.append(('Pedigree', f'Image #{evidence_block.image_id}'))

    if evidence_sources:
        st.markdown('**Evidence Sources:**')
        for source_type, source_value in evidence_sources:
            col1, col2 = st.columns([0.2, 0.8])
            with col1:
                st.markdown(f'*{source_type}*')
            with col2:
                st.text(source_value)

            with st.container(
                horizontal=True,
                vertical_alignment='center',
                horizontal_alignment='right',
            ):
                render_highlight_controls(
                    paper_id,
                    [evidence_block.quote] if evidence_block.quote else [],
                    color_key=f'{paper_id}-{block_id}-color-evidence',
                    button_key_prefix=f'{paper_id}-{block_id}-evidence',
                    image_ids=[evidence_block.image_id]
                    if evidence_block.image_id
                    else [],
                )
    else:
        st.text('No evidence provided')


def render_patient_variant_occurrences_tab() -> None:
    """Display patient-variant links in a table with a detail panel for selected rows."""
    paper_resp: PaperResp = st.session_state['paper_resp']
    if not paper_resp.title:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()
    if paper_resp.pipeline_status != PipelineStatus.COMPLETED:
        st.write(f'Entity Linking not yet completed...')
        st.stop()

    # Load all data sources
    patients: list[PatientResp] = get_patients(paper_resp.id)

    extracted_variant_rows = get_variants(paper_resp.id)
    extracted_variants: list[ExtractedVariantResp] = extracted_variant_rows

    with open(paper_resp.harmonized_variants_json_path, 'r') as f:
        harmonized_data = json.load(f)
        harmonized_variants: list[HarmonizedVariant] = (
            VariantHarmonizationOutput.model_validate(harmonized_data).variants
        )

    with open(paper_resp.patient_variant_links_json_path, 'r') as f:
        link_data = json.load(f)
    links: list[PatientVariantLink] = PatientVariantLinkerOutput.model_validate(
        link_data
    ).links

    # Build a list of rows for the DataFrame
    rows = []
    for link in links:
        patient = patients[link.patient_idx - 1]
        extracted_variant = extracted_variants[link.variant_id - 1]
        harmonized_variant = harmonized_variants[link.variant_id - 1]

        # Determine the variant description
        variant_desc = (
            harmonized_variant.hgvs_g
            or harmonized_variant.hgvs_c
            or harmonized_variant.gnomad_style_coordinates
            or harmonized_variant.rsid
            or harmonized_variant.hgvs_p
            or extracted_variant.variant_evidence.quote
            or f'Variant {link.variant_id}'
        )

        # Format testing methods as a list from EvidenceBlocks
        testing_methods_list = [m.value.value for m in link.testing_methods]

        patient_display = patient.identifier or f'Patient {link.patient_idx}'
        patient_link = f'/paper?paper_id={paper_resp.id}&patient_idx={link.patient_idx}#{patient_display}'
        variant_link = f'/paper?paper_id={paper_resp.id}&variant_id={link.variant_id}#{variant_desc}'
        rows.append(
            {
                'Select': False,
                'Patient': patient_link,
                'Variant': variant_link,
                'Zygosity': link.zygosity.value.value,
                'Inheritance': link.inheritance.value.value,
                'Confidence': link.confidence,
                'Testing Methods': testing_methods_list,
                # Store full objects for detail panel
                '_link': link,
                '_patient': patient,
                '_extracted_variant': extracted_variant,
                '_harmonized_variant': harmonized_variant,
            }
        )

    if not rows:
        st.info('No Patient/Variant links found.')
        st.stop()

    # Create DataFrame for display (exclude internal columns)
    display_rows = [
        {k: v for k, v in row.items() if not k.startswith('_')} for row in rows
    ]
    df = pd.DataFrame(display_rows)

    # Display main table with row selection
    st.subheader('Patient/Variant Occurrences')
    st.caption(f'{len(rows)} total occurrences')

    # Get enum options for multiselect columns
    zygosity_options = [e.value for e in Zygosity]
    inheritance_options = [e.value for e in Inheritance]
    testing_method_options = [e.value for e in TestingMethod]
    confidence_options = ['high', 'moderate', 'low']

    editted_df = st.data_editor(
        df,
        width='stretch',
        hide_index=True,
        disabled=['Patient', 'Variant'],
        column_config={
            'Select': st.column_config.CheckboxColumn('Select', width=5),
            'Patient': st.column_config.LinkColumn(
                'Patient',
                display_text=r'.*?#(.+)$',
            ),
            'Variant': st.column_config.LinkColumn(
                'Variant',
                display_text=r'.*?#(.+)$',
            ),
            'Zygosity': st.column_config.SelectboxColumn(
                'Zygosity',
                options=zygosity_options,
                width='small',
            ),
            'Inheritance': st.column_config.SelectboxColumn(
                'Inheritance',
                options=inheritance_options,
                width='small',
            ),
            'Confidence': st.column_config.SelectboxColumn(
                'Confidence',
                options=confidence_options,
                width='small',
            ),
            'Testing Methods': st.column_config.MultiselectColumn(
                'Testing Methods',
                options=testing_method_options,
                color=['#ffa421', '#803df5', '#00c0f2'],
                format_func=lambda x: x.capitalize(),
            ),
        },
    )

    # Show editable panel when a row is selected
    selected_rows = editted_df[editted_df['Select']].index.tolist()
    if selected_rows:
        idx = selected_rows[0]
        link = rows[idx]['_link']
        patient = rows[idx].get('_patient') or patients[link.patient_idx - 1]
        extracted_variant = rows[idx]['_extracted_variant']
        harmonized_variant = rows[idx]['_harmonized_variant']

        st.divider()
        st.subheader('Occurrence Details')

        # Display patient info and harmonized variant info side by side
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('#### Patient Info')
            patient_data = {
                'Field': [
                    '**Identifier**',
                    '**Proband Status**',
                    '**Affected Status**',
                    '**Sex at Birth**',
                    '**Age at Diagnosis**',
                    '**Age at Report**',
                    '**Country of Origin**',
                    '**Race/Ethnicity**',
                ],
                'Value': [
                    patient.identifier or 'N/A',
                    patient.proband_status.value if patient.proband_status else 'N/A',
                    patient.affected_status.value if patient.affected_status else 'N/A',
                    patient.sex.value if patient.sex else 'N/A',
                    patient.age_diagnosis or 'N/A',
                    patient.age_report or 'N/A',
                    patient.country_of_origin.value
                    if patient.country_of_origin
                    else 'N/A',
                    patient.race_ethnicity.value if patient.race_ethnicity else 'N/A',
                ],
            }
            st.table(pd.DataFrame(patient_data))

        with col2:
            st.markdown('#### Harmonized Variant Info')
            gnomad_coords = (
                f'[{harmonized_variant.gnomad_style_coordinates}]({get_gnomad_url(harmonized_variant.gnomad_style_coordinates)})'
                if harmonized_variant.gnomad_style_coordinates
                else 'N/A'
            )
            variant_data = {
                'Field': [
                    '**HGVS g.**',
                    '**HGVS c.**',
                    '**HGVS p.**',
                    '**rsID**',
                    '**gnomAD-style**',
                ],
                'Value': [
                    harmonized_variant.hgvs_g or 'N/A',
                    harmonized_variant.hgvs_c or 'N/A',
                    harmonized_variant.hgvs_p or 'N/A',
                    harmonized_variant.rsid or 'N/A',
                    gnomad_coords,
                ],
            }
            st.table(pd.DataFrame(variant_data))

        st.divider()

        # Display evidence blocks for zygosity and inheritance
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('#### Zygosity Evidence')
            _render_evidence_block(link.zygosity, paper_resp.id, 'zygosity')

        with col2:
            st.markdown('#### Inheritance Evidence')
            _render_evidence_block(link.inheritance, paper_resp.id, 'inheritance')

        # Display testing methods evidence
        if link.testing_methods:
            st.markdown('#### Testing Methods Evidence')
            for i, method_block in enumerate(link.testing_methods, start=1):
                with st.expander(
                    f'Method {i}: {method_block.value.value}',
                    expanded=False,
                ):
                    _render_evidence_block(method_block, paper_resp.id, f'method_{i}')
