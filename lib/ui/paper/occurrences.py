import pandas as pd
import streamlit as st

from lib.models import PaperResp, PatientResp, VariantResp
from lib.models.evidence_block import EvidenceBlock
from lib.models.patient import AffectedStatus, ProbandStatus
from lib.models.patient_variant_occurrences import Inheritance, TestingMethod, Zygosity
from lib.tasks import TaskType, is_task_completed
from lib.ui.api import (
    get_occurrences,
    get_patients,
    get_variants,
)
from lib.ui.paper.shared import (
    get_gnomad_url,
    render_highlight_controls,
)


def _render_evidence_block(
    evidence_block: EvidenceBlock, paper_id: int, block_id: str
) -> None:
    """Render an EvidenceBlock with reasoning and evidence sources."""

    # Display evidence sources
    evidence_sources = []
    if evidence_block.quote:
        evidence_sources.append(('Text Evidence', evidence_block.quote))
    if evidence_block.table_id is not None:
        evidence_sources.append(
            ('Table', f'Table #{evidence_block.table_id + 1}')
        )  # note table indexes are extracted as zero-indexed, but displayed to user here.
    if evidence_block.image_id is not None:
        evidence_sources.append(('Pedigree', f'Image #{evidence_block.image_id}'))

    if evidence_sources:
        st.markdown('**Evidence Sources:**')
        for source_type, source_value in evidence_sources:
            col1, col2 = st.columns([2, 8])
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
                    blocks=[evidence_block],
                    color_key=f'{paper_id}-{block_id}-{source_type}-color-evidence',
                    button_key_prefix=f'{paper_id}-{block_id}-{source_type}-evidence',
                )
    else:
        st.text('No evidence provided')

    st.text_area('Reasoning', evidence_block.reasoning, height=20, disabled=True)


def render_patient_variant_occurrences_tab() -> None:
    """Display patient-variant links in a table with a detail panel for selected rows."""
    paper_resp: PaperResp = st.session_state['paper_resp']
    if not paper_resp.title:
        st.write(f'{paper_resp.filename} not yet extracted...')
        return
    elif not is_task_completed(paper_resp.tasks, TaskType.PATIENT_VARIANT_OCCURRENCES):
        st.write(f'Patient/Variant Occurrences not yet completed...')
        return

    # Load all data sources via API
    patients: list[PatientResp] = get_patients(paper_resp.id)
    variants: list[VariantResp] = get_variants(paper_resp.id)
    links = get_occurrences(paper_resp.id)

    # Create lookup maps by ID
    patients_by_id = {p.id: p for p in patients}
    variants_by_id = {v.id: v for v in variants}
    links_by_id = {link.id: link for link in links}

    # Build a list of rows for the DataFrame
    rows = []
    for link in links:
        patient = patients_by_id[link.patient_id]
        variant = variants_by_id[link.variant_id]
        harmonized_variant = variant.harmonized_variant
        variant_desc = variant.variant_description

        # Format testing methods as a list of values
        testing_methods_list = link.testing_methods

        patient_display = link.patient_identifier
        patient_link = f'/paper?paper_id={paper_resp.id}&patient_id={link.patient_id}#{patient_display}'
        variant_link = f'/paper?paper_id={paper_resp.id}&variant_id={link.variant_id}#{variant_desc}'

        # Paired Variant: if paired with another variant, create a link to it
        paired_variant_link = ''
        if link.paired_variant_link_id is not None:
            paired_link = links_by_id.get(link.paired_variant_link_id)
            if paired_link:
                paired_variant = variants_by_id.get(paired_link.variant_id)
                if paired_variant:
                    paired_variant_desc = paired_variant.variant_description
                    paired_variant_link = f'/paper?paper_id={paper_resp.id}&variant_id={paired_link.variant_id}#{paired_variant_desc}'

        rows.append(
            {
                'Select': False,
                'Proband': patient.proband_status.value
                if patient.proband_status
                else 'N/A',
                'Affected': patient.affected_status.value
                if patient.affected_status
                else 'N/A',
                'Patient': patient_link,
                'Variant': variant_link,
                'Paired Variant': paired_variant_link,
                'Zygosity': link.zygosity.value,
                'Inheritance': link.inheritance.value,
                'De Novo': link.de_novo,
                'Testing Methods': testing_methods_list,
                'Disease Name': link.disease_name or '',
                # Store full objects for detail panel
                '_link': link,
                '_patient': patient,
                '_variant': variant,
                '_harmonized_variant': harmonized_variant,
            }
        )

    if not rows:
        st.info('No Patient/Variant links found.')
        st.stop()

    # Sort rows by patient_id, then paired_variant_link_id (so pairs are adjacent)
    def sort_key(r: dict) -> tuple:  # type: ignore[no-untyped-def]
        link = r['_link']
        return (link.patient_id, link.paired_variant_link_id or 0)

    rows.sort(key=sort_key)

    # Determine which columns to display based on data
    has_paired_variants = any(row['Paired Variant'] for row in rows)
    has_disease_names = any(row['Disease Name'] for row in rows)

    # Create DataFrame for display (exclude internal columns)
    display_rows = [
        {k: v for k, v in row.items() if not k.startswith('_')} for row in rows
    ]

    # Remove columns that shouldn't be displayed
    if not has_paired_variants:
        for row in display_rows:
            del row['Paired Variant']
    if not has_disease_names:
        for row in display_rows:
            del row['Disease Name']

    df = pd.DataFrame(display_rows)

    # Display main table with row selection
    st.subheader('Patient/Variant Occurrences')
    st.caption(f'{len(rows)} total occurrences')

    # Get enum options for multiselect columns
    zygosity_options = [e.value for e in Zygosity]
    inheritance_options = [e.value for e in Inheritance]
    testing_method_options = [e.value for e in TestingMethod]
    proband_options = [e.value for e in ProbandStatus]
    affected_options = [e.value for e in AffectedStatus]

    # Build column_config with conditional columns
    column_config = {
        'Select': st.column_config.CheckboxColumn('Select', width=5),
        'Proband': st.column_config.SelectboxColumn(
            'Proband',
            options=proband_options,
            width='small',
        ),
        'Affected': st.column_config.SelectboxColumn(
            'Affected',
            options=affected_options,
            width='small',
        ),
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
        'De Novo': st.column_config.CheckboxColumn(
            'De Novo',
            width='small',
        ),
        'Testing Methods': st.column_config.MultiselectColumn(
            'Testing Methods',
            options=testing_method_options,
            color=['#ffa421', '#803df5', '#00c0f2'],
            format_func=lambda x: x.capitalize(),
        ),
    }

    # Add Paired Variant column only if there are paired variants
    if has_paired_variants:
        column_config['Paired Variant'] = st.column_config.LinkColumn(
            'Paired Variant',
            display_text=r'.*?#(.+)$',
        )

    # Add Disease Name column only if there are disease names
    if has_disease_names:
        column_config['Disease Name'] = st.column_config.TextColumn(
            'Disease Name',
            width='medium',
        )

    # Build disabled list, excluding columns that don't exist in the DataFrame
    disabled = ['Proband', 'Affected', 'Patient', 'Variant']
    if has_paired_variants:
        disabled.append('Paired Variant')

    editted_df = st.data_editor(
        df,
        width='stretch',
        hide_index=True,
        disabled=disabled,
        column_config=column_config,
    )

    # Show editable panel when a row is selected
    selected_rows = editted_df[editted_df['Select']].index.tolist()
    if selected_rows:
        idx = selected_rows[0]
        link = rows[idx]['_link']
        patient = rows[idx].get('_patient') or patients_by_id[link.patient_id]
        variant = rows[idx]['_variant']
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
            if harmonized_variant and harmonized_variant.value:
                gnomad_coords = (
                    f'[{harmonized_variant.value.gnomad_style_coordinates}]({get_gnomad_url(harmonized_variant.value.gnomad_style_coordinates)})'
                    if harmonized_variant.value.gnomad_style_coordinates
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
                        harmonized_variant.value.hgvs_g or 'N/A',
                        harmonized_variant.value.hgvs_c or 'N/A',
                        harmonized_variant.value.hgvs_p or 'N/A',
                        harmonized_variant.value.rsid or 'N/A',
                        gnomad_coords,
                    ],
                }
                st.table(pd.DataFrame(variant_data))
            else:
                st.info('Harmonized variant data not available')

        st.divider()

        # Display evidence blocks for zygosity and inheritance
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('#### Zygosity Evidence')
            _render_evidence_block(link.zygosity_evidence, paper_resp.id, 'zygosity')

        with col2:
            st.markdown('#### Inheritance Evidence')
            _render_evidence_block(
                link.inheritance_evidence, paper_resp.id, 'inheritance'
            )

        st.divider()

        # Display de novo evidence
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('#### De Novo')
            st.info(f'**De Novo Status:** {"Yes" if link.de_novo else "No"}')

        with col2:
            st.markdown('#### De Novo Evidence')
            _render_evidence_block(link.de_novo_evidence, paper_resp.id, 'de_novo')

        st.divider()

        # Display testing methods evidence
        if link.testing_methods_evidence:
            st.markdown('#### Testing Methods Evidence')
            for i, testing_method_evidence_block in enumerate(
                link.testing_methods_evidence, start=1
            ):
                with st.expander(
                    f'Method {i}: {testing_method_evidence_block.value.value}',
                    expanded=False,
                ):
                    _render_evidence_block(
                        testing_method_evidence_block, paper_resp.id, f'method_{i}'
                    )

        # Display disease name evidence if present
        if link.disease_name_evidence:
            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.markdown('#### Disease Name')
                st.info(f'**Disease Name:** {link.disease_name or "N/A"}')

            with col2:
                st.markdown('#### Disease Name Evidence')
                _render_evidence_block(
                    link.disease_name_evidence, paper_resp.id, 'disease_name'
                )

        # Display paired variant confidence if present (compound heterozygous pairing)
        if link.paired_variant_link_id and link.paired_variant_confidence:
            st.divider()
            st.markdown('#### Compound Heterozygous Pairing')
            st.markdown(
                f'**Paired with variant:** {link.paired_variant_link_id} '
                f'(Confidence: {link.paired_variant_confidence})'
            )
            if (
                link.paired_variant_confidence_reasoning
                and link.paired_variant_confidence_reasoning.reasoning
            ):
                st.text_area(
                    'Pairing Reasoning',
                    value=link.paired_variant_confidence_reasoning.reasoning,
                    height=15,
                    disabled=True,
                )
