import json

import pandas as pd
import streamlit as st

from lib.agents.patient_extraction_agent import (
    PatientInfo,
    PatientInfoExtractionOutput,
)
from lib.agents.patient_variant_linking_agent import (
    Inheritance,
    LinkType,
    PatientVariantLink,
    PatientVariantLinkerOutput,
    TestingMethod,
    Zygosity,
)
from lib.agents.variant_extraction_agent import Variant, VariantExtractionOutput
from lib.agents.variant_harmonization_agent import (
    HarmonizedVariant,
    VariantHarmonizationOutput,
)
from lib.models import PaperResp, PipelineStatus
from lib.ui.paper.shared import focus_and_switch_tab, get_gnomad_url, highlight_evidence


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
    with open(paper_resp.patient_info_json_path, 'r') as f:
        patient_info_data = json.load(f)
    patients: list[PatientInfo] = PatientInfoExtractionOutput.model_validate(
        patient_info_data
    ).patients

    with open(paper_resp.variants_json_path, 'r') as f:
        extracted_data = json.load(f)
        extracted_variants: list[Variant] = VariantExtractionOutput.model_validate(
            extracted_data
        ).variants

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
        patient = patients[link.patient_id - 1]
        extracted_variant = extracted_variants[link.variant_id - 1]
        harmonized_variant = harmonized_variants[link.variant_id - 1]

        # Determine the variant description
        variant_desc = (
            extracted_variant.variant_description_verbatim
            or harmonized_variant.hgvs_c
            or harmonized_variant.hgvs_p
            or f'Variant {link.variant_id}'
        )

        # Format testing methods as a list
        testing_methods_list = (
            [m.value for m in link.testing_methods] if link.testing_methods else []
        )

        patient_display = patient.identifier or f'Patient {link.patient_id}'
        patient_link = f'/paper?paper_id={paper_resp.id}&patient_id={link.patient_id}#{patient_display}'
        variant_link = f'/paper?paper_id={paper_resp.id}&variant_id={link.variant_id}#{variant_desc}'
        rows.append(
            {
                'Select': False,
                'Patient': patient_link,
                'Variant': variant_link,
                'Zygosity': link.zygosity.value,
                'Inheritance': link.inheritance.value,
                'Confidence': link.confidence,
                'Link Type': link.link_type.value,
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
    link_type_options = [e.value for e in LinkType]
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
            'Link Type': st.column_config.SelectboxColumn(
                'Link Type',
                options=link_type_options,
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
        patient = rows[idx].get('_patient') or patients[link.patient_id - 1]
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
                    '**Normalization Confidence**',
                ],
                'Value': [
                    harmonized_variant.hgvs_g or 'N/A',
                    harmonized_variant.hgvs_c or 'N/A',
                    harmonized_variant.hgvs_p or 'N/A',
                    harmonized_variant.rsid or 'N/A',
                    gnomad_coords,
                    harmonized_variant.normalization_confidence or 'N/A',
                ],
            }
            st.table(pd.DataFrame(variant_data))

        st.divider()

        with st.expander('Evidence Context', expanded=False):
            if link.evidence_context or link.pedigree_image_id:
                with st.container(
                    horizontal=True,
                    vertical_alignment='center',
                    horizontal_alignment='right',
                ):
                    st.text(
                        link.evidence_context or 'Evidence found in Pedigree Image.'
                    )
                    st.space('stretch')
                    st.markdown('Choose Color: ')
                    color_key = (
                        f'{link.patient_id}-{link.variant_id}-color-link-evidence'
                    )
                    if color_key not in st.session_state:
                        st.session_state[color_key] = '#EE00FF'
                    # Color picker — key handles session state automatically
                    color = st.color_picker(
                        'Choose Color:', label_visibility='collapsed', key=color_key
                    )
                    st.button(
                        'Highlight',
                        key=f'{link.patient_id}-{link.variant_id}-highlight-confirm-link-evidence',
                        type='secondary',
                        on_click=highlight_evidence,
                        args=(
                            paper_resp.id,
                            [link.evidence_context] if link.evidence_context else [],
                            [link.pedigree_image_id] if link.pedigree_image_id else [],
                            color,
                        ),
                    )
                    st.button(
                        'Focus & Switch Tab',
                        key=f'{link.patient_id}-{link.variant_id}-focus-confirm-link-evidence',
                        type='secondary',
                        on_click=focus_and_switch_tab,
                        args=(
                            paper_resp.id,
                            [link.evidence_context] if link.evidence_context else [],
                            [link.pedigree_image_id] if link.pedigree_image_id else [],
                            color,
                        ),
                    )
            else:
                st.text('No evidence provided')

        with st.expander('Linkage Notes', expanded=False):
            st.text(link.linkage_notes or 'No notes provided')

        if link.testing_methods_evidence:
            with st.expander('Testing Methods Evidence', expanded=False):
                for i, evidence in enumerate(link.testing_methods_evidence, start=1):
                    st.text(evidence)
