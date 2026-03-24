import json
import time

import pandas as pd
import requests
import streamlit as st

from lib.core.environment import env
from lib.misc.pdf.paths import pdf_image_path
from lib.models import (
    PaperResp,
    PatientResp,
    PatientUpdateRequest,
    PhenotypeLinkingEntry,
    PhenotypeLinkingOutput,
    PipelineStatus,
)
from lib.models.patient import (
    AffectedStatus,
    CountryCode,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)
from lib.ui.api import (
    get_patients,
    get_pedigree,
    grobid_annotations,
    update_patient,
)
from lib.ui.paper.shared import (
    render_evidence_controls,
    render_highlight_controls,
)


def render_patient(
    paper_resp: PaperResp,
    patient: PatientResp,
    expanded: bool,
    key_prefix: str,
    patient_idx: int,
    phenotypes: list[PhenotypeLinkingEntry] | None = None,
) -> None:
    with st.expander(
        f'{patient.identifier or "N/A"}',
        expanded=expanded,
    ):
        col1, col2 = st.columns(2)
        with col1:
            identifier = st.text_input(
                'Patient Identifier',
                patient.identifier,
                key=f'{key_prefix}-identifier',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Patient Identifier Evidence',
                quote=patient.identifier_evidence.quote,
                reasoning=patient.identifier_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-pi-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-pi-evidence',
            )

        col1, col2 = st.columns(2)
        with col1:
            # --- Proband Status
            proband_status = ProbandStatus(
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
                quote=patient.proband_status_evidence.quote,
                reasoning=patient.proband_status_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-ps-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-ps-evidence',
            )

        # --- Affected Status
        col1, col2 = st.columns(2)
        with col1:
            affected_status = AffectedStatus(
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
                quote=patient.affected_status_evidence.quote,
                reasoning=patient.affected_status_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-as-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-as-evidence',
            )

        # --- Sex At Birth
        col1, col2 = st.columns(2)
        with col1:
            sex = SexAtBirth(
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
                quote=patient.sex_evidence.quote,
                reasoning=patient.sex_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-sex-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-sex-evidence',
            )

        # --- Ages
        col1, col2 = st.columns(2)
        with col1:
            age_diagnosis = st.number_input(
                'Age at Diagnosis',
                value=patient.age_diagnosis,
                min_value=0,
                step=1,
                key=f'{key_prefix}-age-diagnosis',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Age at Diagnosis Evidence',
                quote=patient.age_diagnosis_evidence.quote,
                reasoning=patient.age_diagnosis_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-agediag-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agediag-evidence',
            )
        col1, col2 = st.columns(2)
        with col1:
            age_report = st.number_input(
                'Age at Report',
                value=patient.age_report,
                min_value=0,
                step=1,
                key=f'{key_prefix}-age-report',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Age at Report Evidence',
                quote=patient.age_report_evidence.quote,
                reasoning=patient.age_report_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-agereport-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agereport-evidence',
            )
        col1, col2 = st.columns(2)
        with col1:
            age_death = st.number_input(
                'Age at Death',
                value=patient.age_death,
                min_value=0,
                step=1,
                key=f'{key_prefix}-age-death',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                label='Age at Death Evidence',
                quote=patient.age_death_evidence.quote,
                reasoning=patient.age_death_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-agedeath-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agedeath-evidence',
            )

        # --- Country + Ethnicity
        col1, col2 = st.columns(2)
        with col1:
            country_of_origin = CountryCode(
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
                quote=patient.country_of_origin_evidence.quote,
                reasoning=patient.country_of_origin_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-country-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-country-evidence',
            )

        col1, col2 = st.columns(2)
        with col1:
            race_ethnicity = RaceEthnicity(
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
                quote=patient.race_ethnicity_evidence.quote,
                reasoning=patient.race_ethnicity_evidence.reasoning,
                color_key=f'{key_prefix}-{patient.identifier}-color-race-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-race-evidence',
            )

        # --- Save edits: only include changed fields so exclude_unset works
        # Age fields are numeric (int or None). Convert 0 to None for empty values.
        age_diagnosis_val = age_diagnosis if age_diagnosis else None
        age_report_val = age_report if age_report else None
        age_death_val = age_death if age_death else None

        changes: dict[str, str | int | None] = {}
        if identifier != patient.identifier:
            changes['identifier'] = identifier
        if proband_status != patient.proband_status:
            changes['proband_status'] = proband_status.value
        if affected_status != patient.affected_status:
            changes['affected_status'] = affected_status.value
        if sex != patient.sex:
            changes['sex'] = sex.value
        if age_diagnosis_val != patient.age_diagnosis:
            changes['age_diagnosis'] = age_diagnosis_val
        if age_report_val != patient.age_report:
            changes['age_report'] = age_report_val
        if age_death_val != patient.age_death:
            changes['age_death'] = age_death_val
        if country_of_origin != patient.country_of_origin:
            changes['country_of_origin'] = country_of_origin.value
        if race_ethnicity != patient.race_ethnicity:
            changes['race_ethnicity'] = race_ethnicity.value
        update_request = PatientUpdateRequest(**changes)  # type: ignore[arg-type]

        if changes:
            try:
                update_patient(paper_resp.id, patient.patient_idx, update_request)
                st.toast('Saved!', icon=':material/check:')
            except Exception as e:
                st.toast(f'Failed to save: {str(e)}', icon='❌')

        # --- Phenotypes Section
        if phenotypes:
            st.divider()
            _render_patient_phenotypes(
                phenotypes,
                patient_idx,
                key_prefix,
            )


def _render_patient_phenotypes(
    all_phenotypes: list[PhenotypeLinkingEntry],
    patient_idx: int,
    key_prefix: str,
) -> None:
    """Render phenotypes for a specific patient with matched/unmatched tabs."""
    # Filter phenotypes for this patient
    patient_phenotypes = [p for p in all_phenotypes if p.patient_idx == patient_idx]

    if not patient_phenotypes:
        st.info('No phenotypes for this patient.')
        return

    _render_phenotypes_table(
        patient_phenotypes,
        patient_idx,
        key_prefix,
        table_type='patient-phenotypes',
    )


def _render_phenotypes_table(
    phenotypes: list[PhenotypeLinkingEntry],
    patient_idx: int,
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
                }
            )

        rows.append(row)

    # Create DataFrame for display (exclude internal columns)
    display_rows = [
        {k: v for k, v in row.items() if not k.startswith('_')} for row in rows
    ]
    df = pd.DataFrame(display_rows)

    # Display table
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
            ],
            'Value': [
                phenotype.text,
                phenotype.hpo_id or 'N/A',
                phenotype.hpo_name or 'N/A',
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


def render_patients_tab(selected_patient_idx: int | None) -> None:
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
    patients: list[PatientResp] = get_patients(paper_resp.id)

    # Load phenotype linking data
    phenotypes: list[PhenotypeLinkingEntry] | None = None
    with open(paper_resp.phenotype_linking_json_path, 'r') as f:
        phenotype_data = json.load(f)
    phenotypes = PhenotypeLinkingOutput.model_validate(
        phenotype_data
    ).extracted_phenotypes

    # Load pedigree description
    pedigree_description = get_pedigree(paper_resp.id)

    # -----------------------------
    # Display Patients
    # -----------------------------
    indexed_patients = [(p.patient_idx, p) for p in patients]
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
            if selected_patient_idx in {p[0] for p in non_probands}
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
                expanded=(original_idx == selected_patient_idx),
                key_prefix=f'patient-proband-{original_idx}',
                patient_idx=original_idx,
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
                expanded=(original_idx == selected_patient_idx),
                key_prefix=f'patient-non-proband-{original_idx}',
                patient_idx=original_idx,
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
                expanded=(original_idx == selected_patient_idx),
                key_prefix=f'patient-affected-{original_idx}',
                patient_idx=original_idx,
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
                expanded=(original_idx == selected_patient_idx),
                key_prefix=f'patient-unaffected-{original_idx}',
                patient_idx=original_idx,
                phenotypes=phenotypes,
            )
    with pedigree_image_tab:
        if not pedigree_description:
            st.info('No pedigree image available')
        else:
            col1, col2, col3 = st.columns([1, 3, 1])
            with col2:
                st.image(
                    f'{env.PROTOCOL}{env.API_ENDPOINT}{pdf_image_path(paper_resp.id, pedigree_description.image_id)}',
                    width='content',
                )
                st.write(pedigree_description.description)
