import json
import time

import pandas as pd
import requests
import streamlit as st

from lib.core.environment import env
from lib.misc.pdf.paths import pdf_image_path
from lib.models import (
    ExtractedPhenotypeResp,
    PaperResp,
    PatientResp,
    PatientUpdateRequest,
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
    get_phenotypes,
    grobid_annotations,
    update_patient,
)
from lib.ui.paper.shared import (
    render_evidence_controls,
    render_highlight_controls,
)


def _render_patient_phenotypes(
    phenotypes: list[ExtractedPhenotypeResp],
    paper_resp: PaperResp,
    key_prefix: str,
) -> None:
    """Render phenotypes for a specific patient with matched/unmatched tabs."""
    if not phenotypes:
        st.info('No phenotypes for this patient.')
        return

    # Split into matched and unmatched
    matched = [p for p in phenotypes if p.hpo is not None]
    unmatched = [p for p in phenotypes if p.hpo is None]

    tab1, tab2 = st.tabs(
        [f'🔗 Matched to HPO ({len(matched)})', f'❓ Unmatched ({len(unmatched)})']
    )

    with tab1:
        if matched:
            _render_phenotypes_table(matched, paper_resp, key_prefix, show_hpo=True)
        else:
            st.info('No phenotypes matched to HPO.')

    with tab2:
        if unmatched:
            _render_phenotypes_table(unmatched, paper_resp, key_prefix, show_hpo=False)
        else:
            st.info('All phenotypes have been matched to HPO.')


def _render_phenotypes_table(
    phenotypes: list[ExtractedPhenotypeResp],
    paper_resp: PaperResp,
    key_prefix: str,
    show_hpo: bool,
) -> None:
    """Render phenotypes table with detail panel."""
    # Build table rows
    rows = []
    for phenotype in phenotypes:
        row = {
            'Select': False,
            'Phenotype': phenotype.concept,
            'Evidence': phenotype.concept_evidence.quote or '',
            'Reasoning': phenotype.hpo.reasoning or '' if phenotype.hpo else '',
            '_phenotype': phenotype,
        }

        if (
            show_hpo
            and phenotype.hpo
            and phenotype.hpo.value
            and phenotype.hpo.value.id
        ):
            hpo_id_link = f'https://hpo.jax.org/app/browse/term/{phenotype.hpo.value.id}#{phenotype.hpo.value.id}'
            hpo_term_link = f'https://hpo.jax.org/app/browse/term/{phenotype.hpo.value.id}#{phenotype.hpo.value.name}'
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
        'Phenotype': st.column_config.TextColumn('Phenotype', width='large'),
        'Evidence': st.column_config.TextColumn('Evidence', width='medium'),
        'Reasoning': st.column_config.TextColumn('Reasoning', width='medium'),
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
        disabled=['Phenotype', 'Evidence', 'Reasoning']
        + (['HPO ID', 'HPO Term'] if show_hpo else []),
        column_config=column_config,
        key=f'{key_prefix}-phenotypes-editor',
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
                '**Concept**',
                '**HPO ID**',
                '**HPO Term**',
            ],
            'Value': [
                phenotype.concept,
                phenotype.hpo.value.id
                if phenotype.hpo and phenotype.hpo.value and phenotype.hpo.value.id
                else 'N/A',
                phenotype.hpo.value.name
                if phenotype.hpo and phenotype.hpo.value and phenotype.hpo.value.name
                else 'N/A',
            ],
        }
        st.table(pd.DataFrame(details_data))

        (
            col1,
            col2,
            col3,
        ) = st.columns(3)

        with col1:
            if phenotype.concept_evidence.quote:
                with st.expander('Extracted Phenotype Evidence', expanded=False):
                    st.text(phenotype.concept_evidence.quote)
                with st.container(
                    horizontal=True,
                    vertical_alignment='center',
                    horizontal_alignment='right',
                ):
                    render_highlight_controls(
                        paper_resp.id,
                        quote=phenotype.concept_evidence.quote,
                        table_id=phenotype.concept_evidence.table_id,
                        image_id=phenotype.concept_evidence.image_id,
                        color_key=f'{key_prefix}-highlight-color-{phenotype.concept}',
                        button_key_prefix=f'{key_prefix}-highlight-confirm-{phenotype.concept}',
                        disabled=False,
                    )

        # Concept evidence reasoning
        with col2:
            if phenotype.concept_evidence.reasoning:
                with st.expander('Extracted Phenotype Reasoning', expanded=False):
                    st.text(phenotype.concept_evidence.reasoning)

        # HPO matching reasoning
        with col3:
            if phenotype.hpo and phenotype.hpo.reasoning:
                with st.expander('HPO Match Reasoning', expanded=False):
                    st.text(phenotype.hpo.reasoning)


def render_patient(
    paper_resp: PaperResp,
    patient: PatientResp,
    expanded: bool,
    key_prefix: str,
    patient_id: int,
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
                quote=patient.identifier_evidence.quote,
                table_id=patient.identifier_evidence.table_id,
                image_id=patient.identifier_evidence.image_id,
                label='Patient Identifier Evidence',
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
                quote=patient.proband_status_evidence.quote,
                table_id=patient.proband_status_evidence.table_id,
                image_id=patient.proband_status_evidence.image_id,
                label='Proband Status Evidence',
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
                quote=patient.affected_status_evidence.quote,
                table_id=patient.affected_status_evidence.table_id,
                image_id=patient.affected_status_evidence.image_id,
                label='Affected Status Evidence',
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
                quote=patient.sex_evidence.quote,
                table_id=patient.sex_evidence.table_id,
                image_id=patient.sex_evidence.image_id,
                label='Sex At Birth Evidence',
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
                quote=patient.age_diagnosis_evidence.quote,
                table_id=patient.age_diagnosis_evidence.table_id,
                image_id=patient.age_diagnosis_evidence.image_id,
                label='Age at Diagnosis Evidence',
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
                quote=patient.age_report_evidence.quote,
                table_id=patient.age_report_evidence.table_id,
                image_id=patient.age_report_evidence.image_id,
                label='Age at Report Evidence',
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
                quote=patient.age_death_evidence.quote,
                table_id=patient.age_death_evidence.table_id,
                image_id=patient.age_death_evidence.image_id,
                label='Age at Death Evidence',
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
                quote=patient.country_of_origin_evidence.quote,
                table_id=patient.country_of_origin_evidence.table_id,
                image_id=patient.country_of_origin_evidence.image_id,
                label='Country of Origin Evidence',
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
                quote=patient.race_ethnicity_evidence.quote,
                table_id=patient.race_ethnicity_evidence.table_id,
                image_id=patient.race_ethnicity_evidence.image_id,
                label='Race/Ethnicity Evidence',
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
                update_patient(paper_resp.id, patient.id, update_request)
                st.toast('Saved!', icon=':material/check:')
            except Exception as e:
                st.toast(f'Failed to save: {str(e)}', icon='❌')

        # --- Phenotypes Section
        st.divider()
        st.markdown('### Phenotypes')
        try:
            phenotypes = get_phenotypes(paper_resp.id, patient.id)
            _render_patient_phenotypes(phenotypes, paper_resp, key_prefix)
        except Exception as e:
            st.error(f'Failed to load phenotypes: {str(e)}')


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
    patients: list[PatientResp] = get_patients(paper_resp.id)

    # Load pedigree description
    pedigree_description = get_pedigree(paper_resp.id)

    # -----------------------------
    # Display Patients
    # -----------------------------
    indexed_patients = [(p.id, p) for p in patients]
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
        for original_id, patient in probands:
            st.markdown(f'### Patient {original_id}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_id == selected_patient_id),
                key_prefix=f'patient-proband-{original_id}',
                patient_id=original_id,
            )
    with non_proband_tab:
        if not non_probands:
            st.info('No non-probands detected.')
        for original_id, patient in non_probands:
            st.markdown(f'### Patient {original_id}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_id == selected_patient_id),
                key_prefix=f'patient-non-proband-{original_id}',
                patient_id=original_id,
            )
    with affecteds_tab:
        if not affecteds:
            st.info('No affected patients detected.')
        for original_id, patient in affecteds:
            st.markdown(f'### Patient {original_id}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_id == selected_patient_id),
                key_prefix=f'patient-affected-{original_id}',
                patient_id=original_id,
            )
    with unaffecteds_tab:
        if not unaffecteds:
            st.info('No affected patients detected.')
        for original_id, patient in unaffecteds:
            st.markdown(f'### Patient {original_id}')
            render_patient(
                paper_resp,
                patient,
                expanded=(original_id == selected_patient_id),
                key_prefix=f'patient-unaffected-{original_id}',
                patient_id=original_id,
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
