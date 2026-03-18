import json
import time

import pandas as pd
import requests
import streamlit as st

from lib.agents.patient_extraction_agent import (
    AffectedStatus,
    CountryCode,
    PatientInfo,
    PatientInfoExtractionOutput,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)
from lib.core.environment import env
from lib.misc.pdf.paths import pdf_image_path
from lib.models import (
    HpoConfidence,
    PaperResp,
    PhenotypeLinkingEntry,
    PhenotypeLinkingOutput,
    PipelineStatus,
)
from lib.ui.api import get_http_error_detail, grobid_annotations
from lib.ui.paper.shared import (
    render_evidence_controls,
    render_highlight_controls,
)


def render_patient(
    paper_resp: PaperResp,
    patient: PatientInfo,
    expanded: bool,
    key_prefix: str,
    patient_id: int,
    phenotypes: list[PhenotypeLinkingEntry] | None = None,
) -> None:
    with st.expander(
        f'{patient.identifier or "N/A"}',
        expanded=expanded,
    ):
        col1, col2 = st.columns(2)
        with col1:
            patient.identifier = st.text_input(
                'Patient Identifier',
                patient.identifier,
                key=f'{key_prefix}-identifier',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Patient Identifier Evidence',
                evidence_context=patient.identifier_evidence_context,
                reasoning=patient.identifier_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-pi-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-pi-evidence',
            )

        col1, col2 = st.columns(2)
        with col1:
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
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Proband Status Evidence',
                evidence_context=patient.proband_status_evidence_context,
                reasoning=patient.proband_status_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-ps-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-ps-evidence',
            )

        # --- Affected Status
        col1, col2 = st.columns(2)
        with col1:
            patient.affected_status = AffectedStatus(
                st.selectbox(
                    'Affected Status',
                    [a.value for a in AffectedStatus],
                    index=(
                        [a.value for a in AffectedStatus].index(
                            patient.affected_status.value
                        )
                        if patient.affected_status
                        else 0
                    ),
                    key=f'{key_prefix}-affected-status',
                )
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Affected Status Evidence',
                evidence_context=patient.affected_status_evidence_context,
                reasoning=patient.affected_status_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-as-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-as-evidence',
            )

        # --- Sex At Birth
        col1, col2 = st.columns(2)
        with col1:
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
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Sex At Birth Evidence',
                evidence_context=patient.sex_evidence_context,
                reasoning=patient.sex_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-sex-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-sex-evidence',
            )

        # --- Ages
        col1, col2 = st.columns(2)
        with col1:
            patient.age_diagnosis = st.text_input(
                'Age at Diagnosis',
                patient.age_diagnosis or '',
                key=f'{key_prefix}-age-diagnosis',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Age at Diagnosis Evidence',
                evidence_context=patient.age_diagnosis_evidence_context,
                reasoning=patient.age_diagnosis_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-agediag-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agediag-evidence',
            )
        col1, col2 = st.columns(2)
        with col1:
            patient.age_report = st.text_input(
                'Age at Report',
                patient.age_report or '',
                key=f'{key_prefix}-age-report',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Age at Report Evidence',
                evidence_context=patient.age_report_evidence_context,
                reasoning=patient.age_report_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-agereport-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agereport-evidence',
            )
        col1, col2 = st.columns(2)
        with col1:
            patient.age_death = st.text_input(
                'Age at Death',
                patient.age_death or '',
                key=f'{key_prefix}-age-death',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Age at Death Evidence',
                evidence_context=patient.age_death_evidence_context,
                reasoning=patient.age_death_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-agedeath-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agedeath-evidence',
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
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Country of Origin Evidence',
                evidence_context=patient.country_of_origin_evidence_context,
                reasoning=patient.country_of_origin_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-country-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-country-evidence',
            )

        col1, col2 = st.columns(2)
        with col1:
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
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Race/Ethnicity Evidence',
                evidence_context=patient.race_ethnicity_evidence_context,
                reasoning=patient.race_ethnicity_reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-race-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-race-evidence',
            )

        # --- Phenotypes Section
        if phenotypes:
            st.divider()
            _render_patient_phenotypes(
                phenotypes,
                patient_id,
                key_prefix,
            )


def _render_patient_phenotypes(
    all_phenotypes: list[PhenotypeLinkingEntry],
    patient_id: int,
    key_prefix: str,
) -> None:
    """Render phenotypes for a specific patient with matched/unmatched tabs."""
    # Filter phenotypes for this patient
    patient_phenotypes = [p for p in all_phenotypes if p.patient_id == patient_id]

    if not patient_phenotypes:
        st.info('No phenotypes for this patient.')
        return

    # Split into matched and unmatched
    matched = [p for p in patient_phenotypes if p.hpo_id]
    unmatched = [p for p in patient_phenotypes if not p.hpo_id]

    matched_tab, unmatched_tab = st.tabs(
        [
            f'🔗 Matched to HPO ({len(matched)})',
            f'❓ Unmatched ({len(unmatched)})',
        ]
    )

    with matched_tab:
        if not matched:
            st.info('No phenotypes matched to HPO terms.')
        else:
            _render_phenotypes_table(
                matched,
                patient_id,
                key_prefix,
                show_hpo=True,
                table_type='matched-phenotypes',
            )

    with unmatched_tab:
        if not unmatched:
            st.info('All phenotypes were successfully matched to HPO terms.')
        else:
            _render_phenotypes_table(
                unmatched,
                patient_id,
                key_prefix,
                show_hpo=False,
                table_type='unmatched-phenotypes',
            )


def _render_phenotypes_table(
    phenotypes: list[PhenotypeLinkingEntry],
    patient_id: int,
    key_prefix: str,
    show_hpo: bool,
    table_type: str,
) -> None:
    """Render phenotypes table with detail panel."""
    paper_resp = st.session_state.get('paper_resp')
    # Build table rows
    rows = []
    for phenotype in phenotypes:
        row = {
            'Select': False,
            'Phenotype': phenotype.text,
            'Evidence Context': '\n '.join(phenotype.evidence_contexts)
            if phenotype.evidence_contexts
            else '',
            '_phenotype': phenotype,
        }

        if show_hpo:
            hpo_id_link = (
                f'https://hpo.jax.org/app/browse/term/{phenotype.hpo_id}#{phenotype.hpo_id}'
                if phenotype.hpo_id
                else None
            )
            hpo_term_link = (
                f'https://hpo.jax.org/app/browse/term/{phenotype.hpo_id}#{phenotype.hpo_name}'
                if phenotype.hpo_id
                else None
            )
            row.update(
                {
                    'HPO ID': hpo_id_link,
                    'HPO Term': hpo_term_link,
                    'Confidence': phenotype.hpo_confidence.value
                    if phenotype.hpo_confidence
                    else 'N/A',
                }
            )

        rows.append(row)

    # Create DataFrame for display (exclude internal columns)
    display_rows = [
        {k: v for k, v in row.items() if not k.startswith('_')} for row in rows
    ]
    df = pd.DataFrame(display_rows)

    # Display table
    confidence_options = [e.value for e in HpoConfidence]

    column_config = {
        'Select': st.column_config.CheckboxColumn('Select', width='small'),
        'Phenotype': st.column_config.TextColumn(
            'Phenotype',
            width='large',
        ),
    }
    if show_hpo:
        column_config.update(
            {
                'HPO ID': st.column_config.LinkColumn(
                    'HPO ID',
                    width='small',
                    display_text=r'.*?#(.+)$',
                ),
                'HPO Term': st.column_config.LinkColumn(
                    'HPO Term',
                    width='medium',
                    display_text=r'.*?#(.+)$',
                ),
                'Confidence': st.column_config.SelectboxColumn(
                    'Confidence',
                    options=confidence_options,
                    width='small',
                ),
            }
        )

    editted_df = st.data_editor(
        df,
        width='stretch',
        hide_index=True,
        disabled=['Phenotype'] + (['HPO ID', 'HPO Term'] if show_hpo else []),
        column_config=column_config,
        key=f'{key_prefix}-{table_type}-editor',
    )

    # Show detail panel when a row is selected
    selected_rows = editted_df[editted_df['Select']].index.tolist()
    if selected_rows:
        idx = selected_rows[0]
        phenotype = rows[idx]['_phenotype']

        st.divider()
        st.markdown('##### Phenotype Details')

        details_data = {
            'Field': [
                '**Text**',
                '**HPO ID**',
                '**HPO Term**',
                '**HPO Confidence**',
            ],
            'Value': [
                phenotype.text,
                phenotype.hpo_id or 'N/A',
                phenotype.hpo_name or 'N/A',
                phenotype.hpo_confidence.value if phenotype.hpo_confidence else 'N/A',
            ],
        }
        st.table(pd.DataFrame(details_data))

        # Create three horizontal columns
        col1, col2, col3 = st.columns(3)

        # Evidence context
        with col1:
            if phenotype.evidence_contexts:
                with st.expander('Evidence Context', expanded=False):
                    for i, note in enumerate(phenotype.evidence_contexts, 1):
                        st.markdown(f'**Note {i}:** {note}')

        # HPO matching notes
        with col2:
            if phenotype.hpo_reasoning:
                with st.expander('HPO Reasoning', expanded=False):
                    st.text(phenotype.hpo_reasoning)

        # Highlight button with popover
        with col3:
            if paper_resp:
                with st.container(
                    horizontal=True,
                    vertical_alignment='center',
                    horizontal_alignment='right',
                ):
                    render_highlight_controls(
                        paper_resp.id,
                        phenotype.evidence_contexts or [],
                        color_key=f'{key_prefix}-highlight-color-{phenotype.text}',
                        button_key_prefix=f'{key_prefix}-highlight-confirm-{phenotype.text}',
                        disabled=not phenotype.evidence_contexts,
                    )


def render_patients_tab(selected_patient_id: int | None) -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    if not paper_resp.title:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()
    if paper_resp.pipeline_status != PipelineStatus.COMPLETED:
        st.write(f'Entity Linking not yet completed...')
        st.stop()
    # -----------------------------
    # Load patients
    # ---------------
    with open(paper_resp.patient_info_json_path, 'r') as f:
        patient_info_data = json.load(f)
    patients: list[PatientInfo] = PatientInfoExtractionOutput.model_validate(
        patient_info_data
    ).patients

    # Load phenotype linking data
    phenotypes: list[PhenotypeLinkingEntry] | None = None
    with open(paper_resp.phenotype_linking_json_path, 'r') as f:
        phenotype_data = json.load(f)
    phenotypes = PhenotypeLinkingOutput.model_validate(phenotype_data).phenotypes

    # Load pedigree description
    with open(paper_resp.pedigree_descriptions_json_path, 'r') as f:
        pedigree_description = json.load(f)

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
    affecteds = [
        (i, p)
        for i, p in indexed_patients
        if p.affected_status == AffectedStatus.Affected
    ]
    unaffecteds = [
        (i, p)
        for i, p in indexed_patients
        if p.affected_status != AffectedStatus.Affected
    ]
    tabs = [
        f'Probands ({len(probands)})',
        f'Non-Probands ({len(non_probands)})',
        f'Affecteds ({len(affecteds)})',
        f'Unaffecteds ({len(unaffecteds)})',
        'Pedigree Image',
    ]
    proband_tab, non_proband_tab, affecteds_tab, unaffecteds_tab, pedigree_image_tab = (
        st.tabs(
            tabs,
            default=tabs[1]
            if selected_patient_id in {p[0] for p in non_probands}
            else tabs[0],
        )
    )
    with proband_tab:
        if not probands:
            st.info('No probands detected.')
        for original_idx, patient in probands:
            st.markdown(f'### Patient {original_idx}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_idx == selected_patient_id),
                key_prefix=f'patient-proband-{original_idx}',
                patient_id=original_idx,
                phenotypes=phenotypes,
            )
    with non_proband_tab:
        if not non_probands:
            st.info('No non-probands detected.')
        for original_idx, patient in non_probands:
            st.markdown(f'### Patient {original_idx}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_idx == selected_patient_id),
                key_prefix=f'patient-non-proband-{original_idx}',
                patient_id=original_idx,
                phenotypes=phenotypes,
            )
    with affecteds_tab:
        if not affecteds:
            st.info('No affected patients detected.')
        for original_idx, patient in affecteds:
            st.markdown(f'### Patient {original_idx}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_idx == selected_patient_id),
                key_prefix=f'patient-affected-{original_idx}',
                patient_id=original_idx,
                phenotypes=phenotypes,
            )
    with unaffecteds_tab:
        if not unaffecteds:
            st.info('No affected patients detected.')
        for original_idx, patient in unaffecteds:
            st.markdown(f'### Patient {original_idx}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_idx == selected_patient_id),
                key_prefix=f'patient-unaffected-{original_idx}',
                patient_id=original_idx,
                phenotypes=phenotypes,
            )
    with pedigree_image_tab:
        if (
            not pedigree_description['description']
            or not pedigree_description['image_id']
        ):
            st.info('No pedigree image available')
        else:
            col1, col2, col3 = st.columns([1, 3, 1])
            with col2:
                st.image(
                    f'{env.PROTOCOL}{env.API_ENDPOINT}{pdf_image_path(paper_resp.id, int(pedigree_description["image_id"]))}',
                    width='content',
                )
                st.write(pedigree_description['description'])
