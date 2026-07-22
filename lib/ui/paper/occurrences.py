import time

import pandas as pd
import streamlit as st

from lib.models import (
    PaperResp,
    PatientResp,
    PatientVariantOccurrenceUpdateRequest,
    VariantResp,
)
from lib.models.evidence_block import EvidenceBlock
from lib.models.patient import AffectedStatus, ProbandStatus
from lib.models.patient_variant_occurrences import (
    CompoundHetConfidence,
    Inheritance,
    TestingMethod,
    Zygosity,
)
from lib.tasks import TaskType, is_task_completed
from lib.ui.api import (
    get_families,
    get_occurrences,
    get_patients,
    get_variants,
    update_occurrence,
)
from lib.ui.paper.shared import (
    get_gnomad_url,
    render_evidence_controls,
    render_highlight_controls,
)

NO_TESTING_METHOD = 'None'
OCCURRENCES_EDITOR_KEY = 'occurrences-editor'


def _format_variant_with_protein(
    variant: VariantResp, include_protein: bool = False
) -> str:
    """Format variant description with optional protein notation."""
    desc = variant.variant_description
    if include_protein and variant.hgvs_p:
        # If already formatted with parentheses, use as-is
        if variant.hgvs_p.startswith('p.('):
            desc += f' {variant.hgvs_p}'
        else:
            desc += f' p.({variant.hgvs_p})'
    return desc


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
    families = get_families(paper_resp.id)

    # Create lookup maps by ID
    patients_by_id = {p.id: p for p in patients}
    variants_by_id = {v.id: v for v in variants}
    links_by_id = {link.id: link for link in links}
    families_by_id = {f.id: f for f in families}

    # Build a list of rows for the DataFrame
    rows = []
    for link in links:
        patient = patients_by_id[link.patient_id]
        variant = variants_by_id[link.variant_id]
        harmonized_variant = variant.harmonized_variant
        # Show p. notation for paired variants or heterozygous
        show_protein = (
            link.paired_variant_link_id is not None
            or link.zygosity == Zygosity.heterozygous
        )
        variant_desc = _format_variant_with_protein(variant, show_protein)

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
                    # Show p. notation for paired variants
                    paired_variant_desc = _format_variant_with_protein(
                        paired_variant, True
                    )
                    paired_variant_link = f'/paper?paper_id={paper_resp.id}&variant_id={paired_link.variant_id}#{paired_variant_desc}'
                    # Include confidence level if less than Confirmed
                    if (
                        link.paired_variant_confidence
                        and link.paired_variant_confidence
                        != CompoundHetConfidence.confirmed
                    ):
                        confidence_text = (
                            link.paired_variant_confidence.value.capitalize()
                        )
                        paired_variant_link += (
                            f' (Pairing Confidence: {confidence_text})'
                        )

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

    def _on_occurrences_edit() -> None:
        """Persist inline edits made directly in the grid (Zygosity, Inheritance,
        De Novo, Testing Methods are all editable columns above). Mirrors the
        edited_rows/on_change pattern used for the paper dashboard's grid."""
        edited_rows = st.session_state[OCCURRENCES_EDITOR_KEY].get('edited_rows', {})
        errors = []
        for row_idx, cell_changes in edited_rows.items():
            if row_idx >= len(rows):
                continue
            link = rows[row_idx]['_link']
            patch: dict = {}
            if 'Zygosity' in cell_changes:
                patch['zygosity'] = cell_changes['Zygosity']
            if 'Inheritance' in cell_changes:
                patch['inheritance'] = cell_changes['Inheritance']
            if 'De Novo' in cell_changes:
                patch['de_novo'] = bool(cell_changes['De Novo'])
            if 'Testing Methods' in cell_changes:
                patch['testing_methods'] = list(cell_changes['Testing Methods'] or [])
            if patch:
                try:
                    update_occurrence(
                        paper_resp.id,
                        link.id,
                        PatientVariantOccurrenceUpdateRequest(**patch),
                    )
                except Exception as e:
                    errors.append(str(e))
        if errors:
            st.toast(f'Failed to save {len(errors)} row(s): {errors[0]}', icon='❌')
        elif edited_rows:
            st.toast('Saved!', icon=':material/check:')

    editted_df = st.data_editor(
        df,
        width='stretch',
        hide_index=True,
        disabled=disabled,
        column_config=column_config,
        key=OCCURRENCES_EDITOR_KEY,
        on_change=_on_occurrences_edit,
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
            family = families_by_id.get(patient.family_id)
            patient_data = {
                'Field': [
                    '**Identifier**',
                    '**Proband Status**',
                    '**Affected Status**',
                    '**Sex at Birth**',
                    '**Age at Diagnosis**',
                    '**Age at Report**',
                    '**Country of Origin**',
                    '**Race**',
                    '**Ethnicity**',
                    '**Consanguineous**',
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
                    patient.race.value if patient.race else 'N/A',
                    patient.ethnicity.value if patient.ethnicity else 'N/A',
                    ('Yes' if family.consanguinity else 'No') if family else 'N/A',
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
        st.markdown('#### Occurrence Properties')

        # Zygosity
        col1, col2 = st.columns(2)
        with col1:
            zygosity_options = [z.value for z in Zygosity]
            zygosity_val = Zygosity(
                st.selectbox(
                    'Zygosity',
                    zygosity_options,
                    index=zygosity_options.index(link.zygosity.value),
                    key=f'occ-{link.id}-zygosity',
                )
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                block=link.zygosity_evidence,
                label='📋 Evidence & Reasoning',
                color_key=f'occ-{link.id}-zygosity-color',
                button_key_prefix=f'occ-{link.id}-zygosity',
            )

        # Inheritance
        col1, col2 = st.columns(2)
        with col1:
            inheritance_options = [i.value for i in Inheritance]
            inheritance_val = Inheritance(
                st.selectbox(
                    'Inheritance',
                    inheritance_options,
                    index=inheritance_options.index(link.inheritance.value),
                    key=f'occ-{link.id}-inheritance',
                )
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                block=link.inheritance_evidence,
                label='📋 Evidence & Reasoning',
                color_key=f'occ-{link.id}-inheritance-color',
                button_key_prefix=f'occ-{link.id}-inheritance',
            )

        # De Novo
        col1, col2 = st.columns(2)
        with col1:
            de_novo_val = st.checkbox(
                'De Novo',
                value=link.de_novo,
                key=f'occ-{link.id}-de-novo',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                block=link.de_novo_evidence,
                label='📋 Evidence & Reasoning',
                color_key=f'occ-{link.id}-de-novo-color',
                button_key_prefix=f'occ-{link.id}-de-novo',
            )

        # Testing Methods (up to two slots)
        testing_method_options = [NO_TESTING_METHOD] + [m.value for m in TestingMethod]
        testing_method_vals = []
        for method_idx in range(2):
            current = (
                link.testing_methods[method_idx].value
                if method_idx < len(link.testing_methods)
                else NO_TESTING_METHOD
            )
            method_evidence = (
                link.testing_methods_evidence[method_idx]
                if method_idx < len(link.testing_methods_evidence)
                else None
            )
            col1, col2 = st.columns(2)
            with col1:
                selected_method = st.selectbox(
                    f'Testing Method #{method_idx + 1}',
                    testing_method_options,
                    index=testing_method_options.index(current),
                    key=f'occ-{link.id}-testing-method-{method_idx}',
                )
            with col2:
                st.space()
                render_evidence_controls(
                    paper_resp.id,
                    block=method_evidence,
                    label='📋 Evidence & Reasoning',
                    color_key=f'occ-{link.id}-testing-method-{method_idx}-color',
                    button_key_prefix=f'occ-{link.id}-testing-method-{method_idx}',
                )
            if selected_method != NO_TESTING_METHOD:
                testing_method_vals.append(selected_method)

        # Save edits made in the detail panel above.
        detail_changes: dict = {}
        if zygosity_val.value != link.zygosity.value:
            detail_changes['zygosity'] = zygosity_val.value
        if inheritance_val.value != link.inheritance.value:
            detail_changes['inheritance'] = inheritance_val.value
        if de_novo_val != link.de_novo:
            detail_changes['de_novo'] = de_novo_val
        if testing_method_vals != [m.value for m in link.testing_methods]:
            detail_changes['testing_methods'] = testing_method_vals

        if detail_changes:
            try:
                update_occurrence(
                    paper_resp.id,
                    link.id,
                    PatientVariantOccurrenceUpdateRequest(**detail_changes),
                )
                st.toast('Saved!', icon=':material/check:')
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.toast(f'Failed to save: {str(e)}', icon='❌')

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

            # Get the paired variant
            paired_link = links_by_id.get(link.paired_variant_link_id)
            if paired_link:
                paired_variant = variants_by_id.get(paired_link.variant_id)
                if paired_variant:
                    paired_variant_desc = _format_variant_with_protein(
                        paired_variant, True
                    )
                    paired_variant_link_url = f'/paper?paper_id={paper_resp.id}&variant_id={paired_variant.id}'
                    st.markdown(
                        f'**Paired with:** [{paired_variant_desc}]({paired_variant_link_url}) '
                        f'— Confidence: **{link.paired_variant_confidence.capitalize()}**'
                    )

            if link.paired_variant_confidence_reasoning:
                st.text_area(
                    'Pairing Reasoning',
                    value=link.paired_variant_confidence_reasoning.reasoning,
                    height=15,
                    disabled=True,
                )
