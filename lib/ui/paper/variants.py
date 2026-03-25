import json
import re

import pandas as pd
import streamlit as st

from lib.models import PaperResp, PipelineStatus, VariantResp
from lib.models.variant import VariantType
from lib.ui.api import get_variants
from lib.ui.paper.shared import (
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


def render_variants_tab(selected_variant_idx: int | None) -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    if not paper_resp.title:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()
    if paper_resp.pipeline_status != PipelineStatus.COMPLETED:
        st.write(f'Entity Linking not yet completed...')
        st.stop()
    variant_rows = get_variants(paper_resp.id)
    variants: list[VariantResp] = variant_rows
    enriched_variants = [v.enriched_variant for v in variants]

    # Separate variants into pathogenic and other
    pathogenic_indices = [
        i
        for i, ev in enumerate(enriched_variants)
        if ev and _is_pathogenic(ev.pathogenicity)
    ]
    other_indices = [
        i for i in range(len(enriched_variants)) if i not in pathogenic_indices
    ]

    # Create tabs
    tabs = [
        f'🔴 Pathogenic ({len(pathogenic_indices)})',
        f'⚪ Other ({len(other_indices)})',
    ]
    tab_pathogenic, tab_other = st.tabs(
        tabs,
        default=tabs[1]
        if selected_variant_idx and (selected_variant_idx - 1) in other_indices
        else tabs[0],
    )

    # Helper function to render variants for a given set of indices
    def render_variant_list(indices: list[int]) -> None:
        for idx in indices:
            i = idx + 1  # Convert 0-based to 1-based for display
            variant = variants[idx]
            harmonized_variant = variant.harmonized_variant
            enriched_variant = (
                enriched_variants[idx] if idx < len(enriched_variants) else None
            )
            st.markdown(f'### Variant {i}')
            expander_title = (
                (
                    harmonized_variant.hgvs_g
                    or harmonized_variant.hgvs_c
                    or harmonized_variant.gnomad_style_coordinates
                    or harmonized_variant.rsid
                    or harmonized_variant.hgvs_p
                    or variant.variant_evidence.quote
                    or f'Variant {i}'
                )
                if harmonized_variant
                else (variant.variant_evidence.quote or f'Variant {i}')
            )
            with st.expander(
                expander_title,
                expanded=(i == selected_variant_idx),
            ):
                # ======================================================
                # Harmonized Variant (PRIMARY DISPLAY)
                # ======================================================
                with st.container():
                    st.subheader('Harmonized Variant Info')
                    if harmonized_variant:
                        col1, col2, col3 = st.columns([1, 1, 2])
                        gnomad_coords = (
                            f'[{harmonized_variant.gnomad_style_coordinates}]({get_gnomad_url(harmonized_variant.gnomad_style_coordinates)})'
                            if harmonized_variant.gnomad_style_coordinates
                            else 'N/A'
                        )
                        with col1:
                            st.markdown(
                                f'**gnomAD-style coordinates:** {gnomad_coords}'
                            )
                            st.markdown(f'**rsID:** {harmonized_variant.rsid or "N/A"}')
                            st.markdown(f'**CAID:** {harmonized_variant.caid or "N/A"}')
                        with col2:
                            col2.markdown(
                                f'**HGVS c.:** {harmonized_variant.hgvs_c or "N/A"}'
                            )
                            col2.markdown(
                                f'**HGVS p.:** {harmonized_variant.hgvs_p or "N/A"}'
                            )
                            col2.markdown(
                                f'**HGVS g.:** {harmonized_variant.hgvs_g or "N/A"}'
                            )
                        with col3:
                            render_evidence_controls(
                                paper_id=paper_resp.id,
                                label='📋 Evidence & Reasoning',
                                quote=variant.variant_evidence.quote,
                                reasoning=variant.variant_evidence.reasoning,
                                color_key=f'{i}-var-color',
                                button_key_prefix=f'{i}-var',
                            )

                        st.text_area(
                            'Harmonization Reasoning',
                            harmonized_variant.reasoning or '',
                            height=140,
                            disabled=True,
                            key=f'{i}-norm-notes',
                        )
                    else:
                        st.info('Harmonization not yet completed for this variant')

                # ======================================================
                # Variant Type
                # ======================================================
                col1, col2 = st.columns(2)
                with col1:
                    selected_value = VariantType(
                        st.selectbox(
                            'Variant Type',
                            [vt.value for vt in VariantType],
                            index=[vt.value for vt in VariantType].index(
                                variant.variant_type
                            )
                            if variant.variant_type
                            else 0,
                            key=f'{i}-type',
                        )
                    )

                with col2:
                    st.space()
                    render_evidence_controls(
                        paper_id=paper_resp.id,
                        label='📋 Evidence & Reasoning',
                        quote=variant.variant_type_evidence.quote,
                        reasoning=variant.variant_type_evidence.reasoning,
                        color_key=f'{i}-vtype-color',
                        button_key_prefix=f'{i}-vtype',
                    )

                # ======================================================
                # Functional Evidence
                # ======================================================
                col1, col2 = st.columns(2)
                with col1:
                    st.checkbox(
                        'Functional Evidence Present',
                        value=variant.functional_evidence,
                        width='stretch',
                        key=f'{i}-func-ev',
                    )
                with col2:
                    st.space()
                    render_evidence_controls(
                        paper_id=paper_resp.id,
                        label='📋 Evidence & Reasoning',
                        quote=variant.functional_evidence_evidence.quote,
                        reasoning=variant.functional_evidence_evidence.reasoning,
                        color_key=f'{i}-func-ev-color',
                        button_key_prefix=f'{i}-func-ev',
                    )

                #
                # Annotations
                #
                # ======================================================
                # Annotations (ClinVar + gnomAD + In Silico)
                # ======================================================
                with st.container():
                    st.subheader('Annotations')

                    if not enriched_variant:
                        st.info('Enrichment not yet completed for this variant')
                    else:
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

                        clinvar_url = (
                            get_clinvar_url(
                                harmonized_variant.hgvs_g,
                                harmonized_variant.hgvs_c,
                                harmonized_variant.rsid,
                            )
                            if harmonized_variant
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
                # Downloads
                # ======================================================
                col_dl1, col_dl2 = st.columns(2)

                col_dl1.download_button(
                    label='Download Extracted Variant JSON',
                    data=json.dumps(
                        {'variants': [v.model_dump() for v in variants]},
                        indent=2,
                    ),
                    file_name='variants.json',
                    mime='application/json',
                    key=f'{i}-extract-json',
                )

                harmonized_data = {
                    'variants': [
                        v.harmonized_variant.model_dump()
                        for v in variants
                        if v.harmonized_variant
                    ]
                }
                col_dl2.download_button(
                    label='Download Harmonized Variant JSON',
                    data=json.dumps(harmonized_data, indent=2),
                    file_name='harmonized_variants.json',
                    mime='application/json',
                    key=f'{i}-harm-json',
                )

    # Render variants in tabs
    with tab_pathogenic:
        if pathogenic_indices:
            render_variant_list(pathogenic_indices)
        else:
            st.info('No pathogenic variants found.')

    with tab_other:
        if other_indices:
            render_variant_list(other_indices)
        else:
            st.info('No other variants found.')
