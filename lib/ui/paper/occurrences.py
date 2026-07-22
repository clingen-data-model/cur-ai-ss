import time
from typing import Any

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
    HUMAN_EDIT_NOTE_DEFAULT,
    get_gnomad_url,
    render_evidence_controls,
    render_highlight_controls,
)

OCCURRENCES_EDITOR_KEY = 'occurrences-editor'
SELECTED_OCCURRENCE_KEY = 'selected_occurrence_id'


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
    rows: list[dict[str, Any]] = []
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

        # Remember which row is selected by its stable link id, not its row
        # index, so the detail panel keeps showing the right occurrence across
        # the rerun triggered by any edit (row order in `rows` is otherwise
        # not guaranteed to stay identical across reruns).
        for row_idx, cell_changes in edited_rows.items():
            if 'Select' not in cell_changes or row_idx >= len(rows):
                continue
            link_id = rows[row_idx]['_link'].id
            if cell_changes['Select']:
                st.session_state[SELECTED_OCCURRENCE_KEY] = link_id
            elif st.session_state.get(SELECTED_OCCURRENCE_KEY) == link_id:
                st.session_state[SELECTED_OCCURRENCE_KEY] = None

        errors = []
        saved_count = 0
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
            if not patch:
                # Only the (non-persisted) Select checkbox changed - nothing to save.
                continue
            try:
                update_occurrence(
                    paper_resp.id,
                    link.id,
                    PatientVariantOccurrenceUpdateRequest(**patch),
                )
                saved_count += 1
            except Exception as e:
                errors.append(str(e))
        if errors:
            st.toast(f'Failed to save {len(errors)} row(s): {errors[0]}', icon='❌')
        elif saved_count:
            st.toast('Saved!', icon=':material/check:')

    st.data_editor(
        df,
        width='stretch',
        hide_index=True,
        disabled=disabled,
        column_config=column_config,
        key=OCCURRENCES_EDITOR_KEY,
        on_change=_on_occurrences_edit,
    )

    # Show editable panel for the selected row, tracked by link id so it
    # survives the rerun triggered by any edit above.
    selected_occurrence_id = st.session_state.get(SELECTED_OCCURRENCE_KEY)
    idx = next(
        (i for i, row in enumerate(rows) if row['_link'].id == selected_occurrence_id),
        None,
    )
    if idx is not None:
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
            zygosity_note = render_evidence_controls(
                paper_resp.id,
                block=link.zygosity_evidence,
                label='📋 Evidence & Reasoning',
                color_key=f'occ-{link.id}-zygosity-color',
                button_key_prefix=f'occ-{link.id}-zygosity',
                human_edit_note_key=f'occ-{link.id}-zygosity-note',
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
            inheritance_note = render_evidence_controls(
                paper_resp.id,
                block=link.inheritance_evidence,
                label='📋 Evidence & Reasoning',
                color_key=f'occ-{link.id}-inheritance-color',
                button_key_prefix=f'occ-{link.id}-inheritance',
                human_edit_note_key=f'occ-{link.id}-inheritance-note',
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
            de_novo_note = render_evidence_controls(
                paper_resp.id,
                block=link.de_novo_evidence,
                label='📋 Evidence & Reasoning',
                color_key=f'occ-{link.id}-de-novo-color',
                button_key_prefix=f'occ-{link.id}-de-novo',
                human_edit_note_key=f'occ-{link.id}-de-novo-note',
            )

        # Testing Methods (up to two slots). An unset slot is shown as an empty
        # placeholder (index=None) rather than a fake 'None' option in the list,
        # matching the Disease Inheritance Mode selectbox on the metadata page.
        testing_method_options = [m.value for m in TestingMethod]
        testing_method_vals = []
        testing_methods_note_edits = []
        for method_idx in range(2):
            current = (
                link.testing_methods[method_idx].value
                if method_idx < len(link.testing_methods)
                else None
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
                    index=testing_method_options.index(current)
                    if current is not None
                    else None,
                    key=f'occ-{link.id}-testing-method-{method_idx}',
                )
            with col2:
                st.space()
                # The one note covering both slots is shown in both slots'
                # popovers (each needs its own widget key), via the
                # human_edit_note_value override - testing_methods_note lives
                # on the occurrence, not on either per-slot EvidenceBlock.
                note_result = render_evidence_controls(
                    paper_resp.id,
                    block=method_evidence,
                    label='📋 Evidence & Reasoning',
                    color_key=f'occ-{link.id}-testing-method-{method_idx}-color',
                    button_key_prefix=f'occ-{link.id}-testing-method-{method_idx}',
                    human_edit_note_key=f'occ-{link.id}-testing-methods-note-{method_idx}',
                    human_edit_note_value=link.testing_methods_note,
                )
                testing_methods_note_edits.append(note_result)
            if selected_method is not None:
                testing_method_vals.append(selected_method)

        # Whichever popover's note was actually edited wins; if both were
        # touched, the later slot takes precedence.
        testing_methods_note_val = link.testing_methods_note
        for note_edit in testing_methods_note_edits:
            if note_edit and note_edit != link.testing_methods_note:
                testing_methods_note_val = note_edit

        # Save edits made in the detail panel above.
        detail_changes: dict = {}
        if zygosity_val.value != link.zygosity.value:
            detail_changes['zygosity'] = zygosity_val.value
            if not link.zygosity_evidence.human_edit_note:
                detail_changes['zygosity_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if zygosity_note and zygosity_note != link.zygosity_evidence.human_edit_note:
            detail_changes['zygosity_human_edit_note'] = zygosity_note

        if inheritance_val.value != link.inheritance.value:
            detail_changes['inheritance'] = inheritance_val.value
            if not link.inheritance_evidence.human_edit_note:
                detail_changes['inheritance_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            inheritance_note
            and inheritance_note != link.inheritance_evidence.human_edit_note
        ):
            detail_changes['inheritance_human_edit_note'] = inheritance_note

        if de_novo_val != link.de_novo:
            detail_changes['de_novo'] = de_novo_val
            if not link.de_novo_evidence.human_edit_note:
                detail_changes['de_novo_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if de_novo_note and de_novo_note != link.de_novo_evidence.human_edit_note:
            detail_changes['de_novo_human_edit_note'] = de_novo_note

        if testing_method_vals != [m.value for m in link.testing_methods]:
            detail_changes['testing_methods'] = testing_method_vals
            if not link.testing_methods_note:
                detail_changes['testing_methods_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            testing_methods_note_val
            and testing_methods_note_val != link.testing_methods_note
        ):
            detail_changes['testing_methods_note'] = testing_methods_note_val

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
