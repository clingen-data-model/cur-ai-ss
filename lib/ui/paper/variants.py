import re
import time

import pandas as pd
import streamlit as st

from lib.models import PaperResp, VariantResp, VariantUpdateRequest
from lib.models.variant import VariantType
from lib.tasks import TaskType, is_task_completed
from lib.ui.api import get_occurrences, get_variants, update_variant
from lib.ui.paper.shared import (
    HUMAN_EDIT_NOTE_DEFAULT,
    get_clingen_url,
    get_clinvar_url,
    get_gnomad_url,
    render_evidence_controls,
)


def _is_pathogenic(pathogenicity: str | None) -> bool:
    """Check if pathogenicity matches 'pathogenic' (case-insensitive), excluding 'conflicting' and 'No_pathogenic_assertion'."""
    if not pathogenicity:
        return False
    pathogenicity_lower = pathogenicity.lower()
    # Exclude conflicting and No_pathogenic_assertion
    if (
        'conflicting' in pathogenicity_lower
        or 'no_pathogenic_assertion' in pathogenicity_lower
    ):
        return False
    return bool(re.search(r'pathogenic', pathogenicity, re.IGNORECASE))


def render_variants_tab(selected_variant_id: int | None) -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    if not paper_resp.title:
        st.write(f'{paper_resp.filename} not yet extracted...')
        return
    elif not is_task_completed(paper_resp.tasks, TaskType.VARIANT_EXTRACTION):
        st.write(f'Variant Extraction not yet completed...')
        return
    variant_rows = get_variants(paper_resp.id)
    variants: list[VariantResp] = variant_rows
    annotated_variants = [v.annotated_variant for v in variants]

    # Fetch patient-variant links
    patient_variant_links = get_occurrences(paper_resp.id)
    # Create mapping from variant_id to list of links
    links_by_variant: dict[int, list] = {}
    for link in patient_variant_links:
        if link.variant_id not in links_by_variant:
            links_by_variant[link.variant_id] = []
        links_by_variant[link.variant_id].append(link)

    # Separate variants into pathogenic and other by index
    pathogenic_indices = [
        i
        for i, ev in enumerate(annotated_variants)
        if ev and _is_pathogenic(ev.pathogenicity)
    ]
    other_indices = [
        i for i in range(len(annotated_variants)) if i not in pathogenic_indices
    ]

    # Separate variants into main focus and contextual by index
    main_focus_indices = [i for i in range(len(variants)) if variants[i].main_focus]
    contextual_indices = [i for i in range(len(variants)) if not variants[i].main_focus]

    # Create mapping from variant ID to index for quick lookup
    variant_id_to_index: dict[int, int] = {
        variants[i].id: i for i in range(len(variants))
    }

    # Determine which tab should be open and if variant should be expanded
    selected_variant_index: int | None = None
    if selected_variant_id is not None:
        selected_variant_index = variant_id_to_index.get(selected_variant_id)

    # Create tabs
    tabs = [
        f'🔴 Pathogenic ({len(pathogenic_indices)})',
        f'⚪ Other ({len(other_indices)})',
        f'📍 Main Focus ({len(main_focus_indices)})',
        f'📌 Contextual ({len(contextual_indices)})',
    ]
    default_tab = tabs[0]  # Default to Pathogenic
    if selected_variant_index is not None:
        if selected_variant_index in other_indices:
            default_tab = tabs[1]
        elif selected_variant_index in main_focus_indices:
            default_tab = tabs[2]
        elif selected_variant_index in contextual_indices:
            default_tab = tabs[3]

    tab_pathogenic, tab_other, tab_main_focus, tab_contextual = st.tabs(
        tabs,
        default=default_tab,
    )

    # Helper function to render variants for a given set of indices
    def render_variant_list(indices: list[int], tab_name: str) -> None:
        for idx in indices:
            i = idx + 1  # Convert 0-based to 1-based for display
            variant = variants[idx]
            harmonized_variant = variant.harmonized_variant
            annotated_variant = (
                annotated_variants[idx] if idx < len(annotated_variants) else None
            )
            key_prefix = f'{tab_name}-variant-{variant.id}'
            st.markdown(f'### Variant {i}')
            expander_title = (
                (
                    harmonized_variant.value.hgvs_c
                    or harmonized_variant.value.hgvs_g
                    or harmonized_variant.value.gnomad_style_coordinates
                    or harmonized_variant.value.rsid
                    or harmonized_variant.value.hgvs_p
                    or variant.variant_evidence.value
                    or f'Variant {i}'
                )
                if harmonized_variant and harmonized_variant.value
                else (variant.variant_evidence.value or f'Variant {i}')
            )
            with st.expander(
                expander_title,
                expanded=(variant.id == selected_variant_id),
            ):
                # Create tabs for Harmonized vs Raw display
                tab_harmonized, tab_raw = st.tabs(
                    ['🔧 Harmonized', 'Raw (as extracted from the paper)']
                )

                # ======================================================
                # RAW TAB - Show extracted fields from paper
                # ======================================================
                with tab_raw:
                    st.subheader('Extracted Variant Info')

                    # Variant description
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'Variant Description',
                            value=variant.variant_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-variant',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.variant_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-variant-color',
                            button_key_prefix=f'{key_prefix}-raw-variant-ev',
                        )

                    # Transcript
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'Transcript',
                            value=variant.transcript_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-transcript',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.transcript_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-transcript-color',
                            button_key_prefix=f'{key_prefix}-raw-transcript-ev',
                        )

                    # Protein Accession
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'Protein Accession',
                            value=variant.protein_accession_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-protein',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.protein_accession_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-protein-color',
                            button_key_prefix=f'{key_prefix}-raw-protein-ev',
                        )

                    # Genomic Accession
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'Genomic Accession',
                            value=variant.genomic_accession_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-genomic-acc',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.genomic_accession_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-genomic-acc-color',
                            button_key_prefix=f'{key_prefix}-raw-genomic-acc-ev',
                        )

                    # LRG Accession
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'LRG Accession',
                            value=variant.lrg_accession_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-lrg',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.lrg_accession_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-lrg-color',
                            button_key_prefix=f'{key_prefix}-raw-lrg-ev',
                        )

                    # Gene Accession
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'Gene Accession',
                            value=variant.gene_accession_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-gene-acc',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.gene_accession_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-gene-acc-color',
                            button_key_prefix=f'{key_prefix}-raw-gene-acc-ev',
                        )

                    # Genomic Coordinates
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'Genomic Coordinates',
                            value=variant.genomic_coordinates_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-genomic-coords',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.genomic_coordinates_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-genomic-coords-color',
                            button_key_prefix=f'{key_prefix}-raw-genomic-coords-ev',
                        )

                    # Genome Build
                    col1, col2 = st.columns(2)
                    with col1:
                        genome_build_val = (
                            variant.genome_build_evidence.value
                            if variant.genome_build_evidence.value
                            else ''
                        )
                        st.text_input(
                            'Genome Build',
                            value=genome_build_val,
                            disabled=True,
                            key=f'{key_prefix}-raw-genome-build',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.genome_build_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-genome-build-color',
                            button_key_prefix=f'{key_prefix}-raw-genome-build-ev',
                        )

                    # HGVS c.
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'HGVS c.',
                            value=variant.hgvs_c_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-hgvs-c',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.hgvs_c_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-hgvs-c-color',
                            button_key_prefix=f'{key_prefix}-raw-hgvs-c-ev',
                        )

                    # HGVS p.
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'HGVS p.',
                            value=variant.hgvs_p_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-hgvs-p',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.hgvs_p_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-hgvs-p-color',
                            button_key_prefix=f'{key_prefix}-raw-hgvs-p-ev',
                        )

                    # HGVS g.
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'HGVS g.',
                            value=variant.hgvs_g_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-hgvs-g',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.hgvs_g_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-hgvs-g-color',
                            button_key_prefix=f'{key_prefix}-raw-hgvs-g-ev',
                        )

                    # rsID
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'rsID',
                            value=variant.rsid_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-rsid',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.rsid_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-rsid-color',
                            button_key_prefix=f'{key_prefix}-raw-rsid-ev',
                        )

                    # CAID
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            'CAID',
                            value=variant.caid_evidence.value or '',
                            disabled=True,
                            key=f'{key_prefix}-raw-caid',
                        )
                    with col2:
                        st.space()
                        render_evidence_controls(
                            paper_resp.id,
                            block=variant.caid_evidence,
                            label='📋 Evidence & Reasoning',
                            color_key=f'{key_prefix}-raw-caid-color',
                            button_key_prefix=f'{key_prefix}-raw-caid-ev',
                        )

                # ======================================================
                # HARMONIZED TAB - Show harmonized and enriched data
                # ======================================================
                with tab_harmonized:
                    # Inputs for harmonized fields are collected here so they can be
                    # diffed against the current values in the change-detection block below.
                    harmonized_inputs: dict[str, str] = {}
                    with st.container():
                        st.subheader('Harmonized Variant Info')
                        if harmonized_variant and harmonized_variant.value:
                            hv = harmonized_variant.value
                            # gnomAD-style coordinates
                            col1, col2 = st.columns(2)
                            with col1:
                                with st.container(
                                    horizontal=True, vertical_alignment='center'
                                ):
                                    harmonized_inputs['gnomad_style_coordinates'] = (
                                        st.text_input(
                                            'gnomAD-style coordinates',
                                            value=hv.gnomad_style_coordinates or '',
                                            key=f'{key_prefix}-harm-gnomad',
                                        )
                                    )
                                    with st.container(
                                        horizontal=False,
                                    ):
                                        if hv.gnomad_style_coordinates:
                                            st.space()
                                            st.caption(
                                                f'[View in gnomAD]({get_gnomad_url(hv.gnomad_style_coordinates)})'
                                            )
                            with col2:
                                st.space()
                                render_evidence_controls(
                                    paper_resp.id,
                                    block=harmonized_variant,
                                    label='📋 Harmonization Reasoning',
                                    color_key=f'{key_prefix}-harm-gnomad-color',
                                    button_key_prefix=f'{key_prefix}-harm-gnomad-ev',
                                )
                            # rsID
                            col1, col2 = st.columns(2)
                            with col1:
                                harmonized_inputs['rsid'] = st.text_input(
                                    'rsID',
                                    value=hv.rsid or '',
                                    key=f'{key_prefix}-harm-rsid',
                                )
                            with col2:
                                st.space()
                                render_evidence_controls(
                                    paper_resp.id,
                                    block=harmonized_variant,
                                    label='📋 Harmonization Reasoning',
                                    color_key=f'{key_prefix}-harm-rsid-color',
                                    button_key_prefix=f'{key_prefix}-harm-rsid-ev',
                                )
                            # CAID
                            col1, col2 = st.columns(2)
                            with col1:
                                with st.container(
                                    horizontal=True, vertical_alignment='center'
                                ):
                                    harmonized_inputs['caid'] = st.text_input(
                                        'CAID',
                                        value=hv.caid or '',
                                        key=f'{key_prefix}-harm-caid',
                                    )
                                    with st.container(
                                        horizontal=False,
                                    ):
                                        if hv.caid:
                                            st.space()
                                            st.caption(
                                                f'[View in ClinGen]({get_clingen_url(hv.caid)})'
                                            )
                            with col2:
                                st.space()
                                render_evidence_controls(
                                    paper_resp.id,
                                    block=harmonized_variant,
                                    label='📋 Harmonization Reasoning',
                                    color_key=f'{key_prefix}-harm-caid-color',
                                    button_key_prefix=f'{key_prefix}-harm-caid-ev',
                                )
                            # HGVS c.
                            col1, col2 = st.columns(2)
                            with col1:
                                harmonized_inputs['hgvs_c'] = st.text_input(
                                    'HGVS c.',
                                    value=hv.hgvs_c or '',
                                    key=f'{key_prefix}-harm-hgvs-c',
                                )
                            with col2:
                                st.space()
                                render_evidence_controls(
                                    paper_resp.id,
                                    block=harmonized_variant,
                                    label='📋 Harmonization Reasoning',
                                    color_key=f'{key_prefix}-harm-hgvs-c-color',
                                    button_key_prefix=f'{key_prefix}-harm-hgvs-c-ev',
                                )
                            # HGVS p.
                            col1, col2 = st.columns(2)
                            with col1:
                                harmonized_inputs['hgvs_p'] = st.text_input(
                                    'HGVS p.',
                                    value=hv.hgvs_p or '',
                                    key=f'{key_prefix}-harm-hgvs-p',
                                )
                            with col2:
                                st.space()
                                render_evidence_controls(
                                    paper_resp.id,
                                    block=harmonized_variant,
                                    label='📋 Harmonization Reasoning',
                                    color_key=f'{key_prefix}-harm-hgvs-p-color',
                                    button_key_prefix=f'{key_prefix}-harm-hgvs-p-ev',
                                )
                            # HGVS g.
                            col1, col2 = st.columns(2)
                            with col1:
                                harmonized_inputs['hgvs_g'] = st.text_input(
                                    'HGVS g.',
                                    value=hv.hgvs_g or '',
                                    key=f'{key_prefix}-harm-hgvs-g',
                                )
                            with col2:
                                st.space()
                                render_evidence_controls(
                                    paper_resp.id,
                                    block=harmonized_variant,
                                    label='📋 Harmonization Reasoning',
                                    color_key=f'{key_prefix}-harm-hgvs-g-color',
                                    button_key_prefix=f'{key_prefix}-harm-hgvs-g-ev',
                                )
                        else:
                            st.info('Harmonization not yet completed for this variant')

                st.divider()
                st.subheader('Variant Properties')

                # ======================================================
                # Variant Type
                # ======================================================
                col1, col2 = st.columns(2)
                with col1:
                    variant_type_val = VariantType(
                        st.selectbox(
                            'Variant Type',
                            [vt.value for vt in VariantType],
                            index=[vt.value for vt in VariantType].index(
                                variant.variant_type
                            )
                            if variant.variant_type
                            else 0,
                            key=f'{key_prefix}-type',
                        )
                    )

                with col2:
                    st.space()
                    vtype_note = render_evidence_controls(
                        paper_resp.id,
                        block=variant.variant_type_evidence,
                        label='📋 Evidence & Reasoning',
                        color_key=f'{key_prefix}-vtype-color',
                        button_key_prefix=f'{key_prefix}-vtype',
                        human_edit_note_key=f'{key_prefix}-vtype-note',
                    )

                # ======================================================
                # Functional Evidence
                # ======================================================
                col1, col2 = st.columns(2)
                with col1:
                    functional_evidence_val = st.checkbox(
                        'Functional Evidence Present',
                        value=variant.functional_evidence,
                        width='stretch',
                        key=f'{key_prefix}-func-ev',
                    )
                with col2:
                    st.space()
                    func_ev_note = render_evidence_controls(
                        paper_resp.id,
                        block=variant.functional_evidence_evidence,
                        label='📋 Evidence & Reasoning',
                        color_key=f'{key_prefix}-func-ev-color',
                        button_key_prefix=f'{key_prefix}-func-ev',
                        human_edit_note_key=f'{key_prefix}-func-ev-note',
                    )

                # ======================================================
                # Main Focus
                # ======================================================
                col1, col2 = st.columns(2)
                with col1:
                    main_focus_val = st.checkbox(
                        'Main Focus of Study',
                        value=variant.main_focus,
                        width='stretch',
                        key=f'{key_prefix}-main-focus',
                    )
                with col2:
                    st.space()
                    main_focus_note = render_evidence_controls(
                        paper_resp.id,
                        block=variant.main_focus_evidence,
                        label='📋 Evidence & Reasoning',
                        color_key=f'{key_prefix}-main-focus-color',
                        button_key_prefix=f'{key_prefix}-main-focus',
                        human_edit_note_key=f'{key_prefix}-main-focus-note',
                    )

                # ======================================================
                # Save edits (change detection → PATCH)
                # ======================================================
                changes: dict = {}

                # Extracted fields
                if variant_type_val.value != variant.variant_type:
                    changes['variant_type'] = variant_type_val.value
                    if not variant.variant_type_evidence.human_edit_note:
                        changes['variant_type_human_edit_note'] = (
                            HUMAN_EDIT_NOTE_DEFAULT
                        )
                if (
                    vtype_note
                    and vtype_note != variant.variant_type_evidence.human_edit_note
                ):
                    changes['variant_type_human_edit_note'] = vtype_note

                if functional_evidence_val != variant.functional_evidence:
                    changes['functional_evidence'] = functional_evidence_val
                    if not variant.functional_evidence_evidence.human_edit_note:
                        changes['functional_evidence_human_edit_note'] = (
                            HUMAN_EDIT_NOTE_DEFAULT
                        )
                if (
                    func_ev_note
                    and func_ev_note
                    != variant.functional_evidence_evidence.human_edit_note
                ):
                    changes['functional_evidence_human_edit_note'] = func_ev_note

                if main_focus_val != variant.main_focus:
                    changes['main_focus'] = main_focus_val
                    if not variant.main_focus_evidence.human_edit_note:
                        changes['main_focus_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
                if (
                    main_focus_note
                    and main_focus_note != variant.main_focus_evidence.human_edit_note
                ):
                    changes['main_focus_human_edit_note'] = main_focus_note

                # Harmonized fields (no per-field evidence, no human_edit_note).
                if harmonized_variant and harmonized_variant.value:
                    hv = harmonized_variant.value
                    harmonized_changes: dict[str, str | None] = {}
                    for field, raw_val in harmonized_inputs.items():
                        new_val = raw_val or None
                        if new_val != getattr(hv, field):
                            harmonized_changes[field] = new_val
                    if harmonized_changes:
                        changes['harmonized_variant'] = harmonized_changes

                if changes:
                    update_request = VariantUpdateRequest(**changes)
                    try:
                        update_variant(paper_resp.id, variant.id, update_request)
                        st.toast('Saved!', icon=':material/check:')
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.toast(f'Failed to save: {str(e)}', icon='❌')

                #
                # Annotations
                #
                # ======================================================
                # Annotations (ClinVar + gnomAD + In Silico)
                # ======================================================
                with st.container():
                    st.subheader('Annotations')

                    if not annotated_variant:
                        st.info('Enrichment not yet completed for this variant')
                    else:
                        ev = annotated_variant

                        # ----------------------------
                        # ClinVar
                        # ----------------------------
                        st.markdown('#### ClinVar')

                        stars_display = (
                            '⭐' * ev.stars
                            if ev.stars is not None and ev.stars > 0
                            else ('0⭐' if ev.stars == 0 else 'N/A')
                        )

                        clinvar_url = (
                            get_clinvar_url(
                                harmonized_variant.value.hgvs_g,
                                harmonized_variant.value.hgvs_c,
                                harmonized_variant.value.rsid,
                            )
                            if harmonized_variant and harmonized_variant.value
                            else None
                        )
                        clinvar_df = pd.DataFrame(
                            [
                                {
                                    'Pathogenicity': (
                                        f'{clinvar_url}#{ev.pathogenicity}'
                                        if clinvar_url and ev.pathogenicity
                                        else (ev.pathogenicity or 'N/A')
                                    ),
                                    'Submissions': ev.submissions or 'N/A',
                                    'Review Status': stars_display,
                                }
                            ]
                        )

                        st.dataframe(
                            clinvar_df,
                            width='stretch',
                            hide_index=True,
                            column_config={
                                'Pathogenicity': st.column_config.LinkColumn(
                                    'Pathogenicity',
                                    display_text=r'.*?#(.+)$',
                                )
                            },
                        )

                        # ----------------------------
                        # In Silico Predictors
                        # ----------------------------
                        st.markdown(
                            '#### In Silico Scores',
                        )

                        if ev.spliceai:
                            spliceai_display = (
                                f'{ev.spliceai.get("max_score", 0):.3f}'
                                + (
                                    f' | {ev.spliceai.get("effect_type")}'
                                    if ev.spliceai.get('effect_type')
                                    else ''
                                )
                                + (
                                    f' @ {ev.spliceai.get("position")}'
                                    if ev.spliceai.get('position') is not None
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

                        st.dataframe(in_silico_df, width='stretch', hide_index=True)

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

                        st.dataframe(gnomad_df, width='stretch', hide_index=True)

                # ======================================================
                # Associated Patients
                # ======================================================
                variant_links = links_by_variant.get(variant.id, [])
                if variant_links:
                    with st.container():
                        st.subheader('Associated Patients')
                        for link in variant_links:
                            st.markdown(
                                f'- Patient "{link.patient_identifier}" w/ Zygosity {link.zygosity.value}'
                            )

    # Render variants in tabs
    with tab_pathogenic:
        if pathogenic_indices:
            render_variant_list(pathogenic_indices, 'pathogenic')
        else:
            st.info('No pathogenic variants found.')

    with tab_other:
        if other_indices:
            render_variant_list(other_indices, 'other')
        else:
            st.info('No other variants found.')

    with tab_main_focus:
        if main_focus_indices:
            render_variant_list(main_focus_indices, 'main-focus')
        else:
            st.info('No main focus variants found.')

    with tab_contextual:
        if contextual_indices:
            render_variant_list(contextual_indices, 'contextual')
        else:
            st.info('No contextual variants found.')
