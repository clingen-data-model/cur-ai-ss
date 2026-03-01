import json

import pandas as pd
import streamlit as st

from lib.agents.variant_enrichment_agent import EnrichedVariant, VariantEnrichmentOutput
from lib.agents.variant_extraction_agent import (
    HgvsInferenceConfidence,
    Variant,
    VariantExtractionOutput,
    VariantType,
)
from lib.agents.variant_harmonization_agent import (
    HarmonizedVariant,
    VariantHarmonizationOutput,
)
from lib.ui.paper.header import PaperQueryParams, render_paper_header
from lib.models import PipelineStatus

paper_query_params = PaperQueryParams.from_query_params()
paper, paper_resp, paper_extraction_output, center = render_paper_header()
with center:
    if not paper_extraction_output:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()
    if paper_resp.pipeline_status != PipelineStatus.COMPLETED:
        st.write(f'Entity Linking not yet completed...')
        st.stop()
    with open(paper.variants_json_path, 'r') as f:
        extracted_data = json.load(f)
        extracted_variants: list[Variant] = VariantExtractionOutput.model_validate(
            extracted_data
        ).variants
    with open(paper.harmonized_variants_json_path, 'r') as f:
        harmonized_data = json.load(f)
        harmonized_variants: list[HarmonizedVariant] = (
            VariantHarmonizationOutput.model_validate(harmonized_data).variants
        )
    with open(paper.enriched_variants_json_path, 'r') as f:
        enriched_data = json.load(f)
        enriched_variants: list[EnrichedVariant] = (
            VariantEnrichmentOutput.model_validate(enriched_data).variants
        )
    for i, harmonized_variant in enumerate(harmonized_variants, start=1):
        extracted_variant = extracted_variants[i - 1]
        enriched_variant = enriched_variants[i - 1]
        st.markdown(f'### Variant {i}')
        with st.expander(
            extracted_variant.variant_description_verbatim
            or harmonized_variant.hgvs_c
            or harmonized_variant.hgvs_p
            or 'Variant',
            expanded=(i == paper_query_params.variant_id),
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

                col2.markdown(f'**HGVS c.:** {harmonized_variant.hgvs_c or "N/A"}')
                col2.markdown(f'**HGVS p.:** {harmonized_variant.hgvs_p or "N/A"}')
                col2.markdown(f'**HGVS g.:** {harmonized_variant.hgvs_g or "N/A"}')

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

                st.dataframe(clinvar_df, width='stretch', hide_index=True)

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
                            'AlphaMissense Class': ev.alphamissense_class or 'N/A',
                            'AlphaMissense Score': round(ev.alphamissense_score, 3)
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
                            'Popmax Population': ev.gnomad_popmax_population or 'N/A',
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
