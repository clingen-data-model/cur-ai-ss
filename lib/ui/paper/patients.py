import json
import time
from collections import defaultdict

import pandas as pd
import requests
import streamlit as st

from lib.core.environment import env
from lib.misc.pdf.paths import pdf_image_path
from lib.models import (
    FamilyResp,
    PaperResp,
    PatientResp,
    PatientUpdateRequest,
    PhenotypeResp,
)
from lib.models.patient import (
    AffectedStatus,
    AgeUnit,
    CountryCode,
    ProbandStatus,
    RaceEthnicity,
    RelationshipToProband,
    SexAtBirth,
    TwinType,
)
from lib.tasks import TaskType, is_task_completed
from lib.ui.api import (
    enqueue_paper_task,
    get_families,
    get_patients,
    get_pedigree,
    get_phenotypes,
    grobid_annotations,
    update_patient,
)
from lib.ui.paper.shared import (
    HUMAN_EDIT_NOTE_DEFAULT,
    render_evidence_controls,
    render_highlight_controls,
)

PATIENTS_KEY = 'patients'
FAMILIES_KEY = 'families'


def _render_patient_phenotypes(
    phenotypes: list[PhenotypeResp],
    paper_resp: PaperResp,
    key_prefix: str,
    patient_id: int,
) -> None:
    """Render phenotypes for a specific patient with matched/unmatched tabs."""
    if not phenotypes:
        st.info('No phenotypes for this patient.')
        return

    # Split into matched and unmatched
    matched = [p for p in phenotypes if p.hpo.value is not None]
    unmatched = [p for p in phenotypes if p.hpo.value is None]

    tab1, tab2 = st.tabs(
        [f'🔗 Matched to HPO ({len(matched)})', f'❓ Unmatched ({len(unmatched)})']
    )

    with tab1:
        if matched:
            _render_phenotypes_table(
                matched,
                paper_resp,
                f'{key_prefix}-matched',
                show_hpo=True,
                patient_id=patient_id,
            )
        else:
            st.info('No phenotypes matched to HPO.')

    with tab2:
        if unmatched:
            _render_phenotypes_table(
                unmatched,
                paper_resp,
                f'{key_prefix}-unmatched',
                show_hpo=False,
                patient_id=patient_id,
            )
        else:
            st.info('All phenotypes have been matched to HPO.')


def _render_phenotypes_table(
    phenotypes: list[PhenotypeResp],
    paper_resp: PaperResp,
    key_prefix: str,
    show_hpo: bool,
    patient_id: int,
) -> None:
    """Render phenotypes table grouped by HPO term with detail panel."""
    # Group matched phenotypes by HPO ID
    if show_hpo:
        hpo_groups: dict[str, list[PhenotypeResp]] = defaultdict(list)
        for phenotype in phenotypes:
            if phenotype.hpo and phenotype.hpo.value and phenotype.hpo.value.id:
                hpo_groups[phenotype.hpo.value.id].append(phenotype)

        # Build rows from grouped phenotypes
        rows = []
        for hpo_id, group in hpo_groups.items():
            first_phenotype = group[0]
            all_concepts = ', '.join(p.concept for p in group)
            row = {
                'Select': False,
                'Phenotype': all_concepts,
                '_phenotypes': group,
            }
            if (
                first_phenotype.hpo
                and first_phenotype.hpo.value
                and first_phenotype.hpo.value.id
            ):
                hpo_id_link = f'https://hpo.jax.org/app/browse/term/{first_phenotype.hpo.value.id}#{first_phenotype.hpo.value.id}'
                hpo_term_link = f'https://hpo.jax.org/app/browse/term/{first_phenotype.hpo.value.id}#{first_phenotype.hpo.value.name}'
                row.update(
                    {
                        'HPO ID': hpo_id_link,
                        'HPO Term': hpo_term_link,
                    }
                )
            rows.append(row)
    else:
        # For unmatched, keep individual phenotypes
        rows = [
            {
                'Select': False,
                'Phenotype': phenotype.concept,
                '_phenotypes': [phenotype],
            }
            for phenotype in phenotypes
        ]

    # Create DataFrame for display (exclude internal columns)
    display_rows = [
        {k: v for k, v in row.items() if not k.startswith('_')} for row in rows
    ]
    df = pd.DataFrame(display_rows)

    # Display table
    column_config = {
        'Select': st.column_config.CheckboxColumn('Select', width='small'),
        'Phenotype': st.column_config.TextColumn('Phenotype', width='large'),
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
        key=f'{key_prefix}-phenotypes-editor',
    )

    # Show detail panel when a row is selected
    selected_rows = editted_df[editted_df['Select']].index.tolist()
    if selected_rows:
        idx = selected_rows[0]
        grouped_phenotypes = rows[idx]['_phenotypes']
        first_phenotype = grouped_phenotypes[0]

        st.divider()
        st.markdown('##### Phenotype Details')

        # Show grouped concepts
        details_data = {
            'Field': ['**Concepts**', '**HPO ID**', '**HPO Term**'],
            'Value': [
                ', '.join(p.concept for p in grouped_phenotypes),
                first_phenotype.hpo.value.id
                if first_phenotype.hpo
                and first_phenotype.hpo.value
                and first_phenotype.hpo.value.id
                else 'N/A',
                first_phenotype.hpo.value.name
                if first_phenotype.hpo
                and first_phenotype.hpo.value
                and first_phenotype.hpo.value.name
                else 'N/A',
            ],
        }
        st.table(pd.DataFrame(details_data))

        # Show all evidence blocks for grouped phenotypes
        (
            col1,
            col2,
            col3,
        ) = st.columns(3)

        with col1:
            # Collect all evidence blocks from grouped phenotypes
            evidence_blocks = [p.concept_evidence for p in grouped_phenotypes]

            if evidence_blocks:
                with st.expander('Extracted Phenotype Evidence', expanded=False):
                    for block in evidence_blocks:
                        if block.quote:
                            st.text(block.quote)
                with st.container(
                    horizontal=True,
                    vertical_alignment='center',
                    horizontal_alignment='right',
                ):
                    render_highlight_controls(
                        paper_resp.id,
                        blocks=evidence_blocks,
                        color_key=f'{key_prefix}-highlight-color-{first_phenotype.id}',
                        button_key_prefix=f'{key_prefix}-highlight-confirm-{first_phenotype.id}',
                        disabled=False,
                    )

        # Concept evidence reasoning
        with col2:
            reasoning_blocks = [
                p.concept_evidence.reasoning
                for p in grouped_phenotypes
                if p.concept_evidence.reasoning
            ]
            if reasoning_blocks:
                with st.expander('Extracted Phenotype Reasoning', expanded=False):
                    for reasoning in reasoning_blocks:
                        st.text(reasoning)

        # HPO matching reasoning
        with col3:
            if first_phenotype.hpo and first_phenotype.hpo.reasoning:
                with st.expander('HPO Match Reasoning', expanded=False):
                    st.text(first_phenotype.hpo.reasoning)
            if st.button(
                '🔄 Re-link HPO',
                key=f'{key_prefix}-relink-hpo-{first_phenotype.id}',
            ):
                enqueue_paper_task(
                    paper_resp.id,
                    TaskType.HPO_LINKING,
                    patient_id=patient_id,
                    phenotype_id=first_phenotype.id,
                )
                st.success('HPO linking task enqueued')


def _render_family_group(
    paper_resp: PaperResp,
    family: FamilyResp,
    patients_in_family: list[tuple[int, PatientResp]],
    selected_patient_id: int | None,
    tab_key: str,
) -> None:
    """Render a family with multiple patients."""
    st.markdown(f'### {family.identifier}')
    with st.expander(
        'View Family',
        expanded=any(pid == selected_patient_id for pid, _ in patients_in_family),
    ):
        # Family identifier + evidence
        col1, col2 = st.columns(2)
        with col1:
            st.text_input(
                'Family Identifier',
                family.identifier,
                disabled=True,
                key=f'{tab_key}-fam-{family.id}-identifier',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                block=family.identifier_evidence,
                label='Family Identifier Evidence',
                color_key=f'{tab_key}-fam-{family.id}-color',
                button_key_prefix=f'{tab_key}-fam-{family.id}-btn',
            )

        # Patients
        for patient_id, patient in patients_in_family:
            st.markdown(f'#### {patient.identifier}')
            render_patient(
                paper_resp,
                patient,
                expanded=(patient_id == selected_patient_id),
                key_prefix=f'{tab_key}-{patient_id}',
                patient_id=patient_id,
            )


def _render_patients_grouped_by_family(
    paper_resp: PaperResp,
    families: list[FamilyResp],
    patients: list[tuple[int, PatientResp]],
    selected_patient_id: int | None,
    tab_key: str,
) -> None:
    """Render patients grouped by family."""
    family_map = {f.id: f for f in families}
    # Group patients by family_id
    by_family: dict[int, list[tuple[int, PatientResp]]] = defaultdict(list)
    for patient_id, patient in patients:
        by_family[patient.family_id].append((patient_id, patient))

    for family_id, group in sorted(by_family.items()):
        family = family_map.get(family_id)
        if len(group) > 1 and family:
            _render_family_group(
                paper_resp, family, group, selected_patient_id, tab_key
            )
        else:
            # Single patient: render as-is (family assignment evidence already in render_patient)
            patient_id, patient = group[0]
            st.markdown(f'### {patient.identifier}')
            render_patient(
                paper_resp,
                patient,
                expanded=(patient_id == selected_patient_id),
                key_prefix=f'{tab_key}-{patient_id}',
                patient_id=patient_id,
            )


def render_patient(
    paper_resp: PaperResp,
    patient: PatientResp,
    expanded: bool,
    key_prefix: str,
    patient_id: int,
) -> None:
    with st.expander(
        'View Patient Metadata',
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
            identifier_note = render_evidence_controls(
                paper_resp.id,
                block=patient.identifier_evidence,
                label='Patient Identifier Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-pi-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-pi-evidence',
                human_edit_note_key=f'{key_prefix}-identifier-note',
            )

        col1, col2 = st.columns(2)
        with col1:
            st.text_input(
                'Family Identifier',
                patient.family_identifier,
                disabled=True,
                key=f'{key_prefix}-family-identifier',
            )
        with col2:
            st.space()
            render_evidence_controls(
                paper_resp.id,
                block=patient.family_assignment_evidence,
                label='Family Assignment Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-fam-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-fam-evidence',
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
            proband_status_note = render_evidence_controls(
                paper_resp.id,
                block=patient.proband_status_evidence,
                label='Proband Status Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-ps-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-ps-evidence',
                human_edit_note_key=f'{key_prefix}-proband-status-note',
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
            affected_status_note = render_evidence_controls(
                paper_resp.id,
                block=patient.affected_status_evidence,
                label='Affected Status Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-as-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-as-evidence',
                human_edit_note_key=f'{key_prefix}-affected-status-note',
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
            sex_note = render_evidence_controls(
                paper_resp.id,
                block=patient.sex_evidence,
                label='Sex At Birth Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-sex-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-sex-evidence',
                human_edit_note_key=f'{key_prefix}-sex-note',
            )

        # --- Ages
        col1, col2 = st.columns(2)
        with col1:
            age_col, unit_col = st.columns([2, 1])
            with age_col:
                age_diagnosis = st.number_input(
                    'Age at Diagnosis',
                    value=patient.age_diagnosis,
                    min_value=0,
                    step=1,
                    key=f'{key_prefix}-age-diagnosis',
                )
            with unit_col:
                age_unit_options = [None] + [u.value for u in AgeUnit]
                age_diagnosis_current = (
                    patient.age_diagnosis_unit.value
                    if patient.age_diagnosis_unit
                    else None
                )
                age_diagnosis_idx = (
                    age_unit_options.index(age_diagnosis_current)
                    if age_diagnosis_current in age_unit_options
                    else 0
                )
                age_diagnosis_unit = st.selectbox(
                    'Unit',
                    options=age_unit_options,
                    index=age_diagnosis_idx,
                    key=f'{key_prefix}-age-diagnosis-unit',
                )
        with col2:
            st.space()
            age_diagnosis_note = render_evidence_controls(
                paper_resp.id,
                block=patient.age_diagnosis_evidence,
                label='Age at Diagnosis Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-agediag-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agediag-evidence',
                human_edit_note_key=f'{key_prefix}-age-diagnosis-note',
            )
        col1, col2 = st.columns(2)
        with col1:
            age_col, unit_col = st.columns([2, 1])
            with age_col:
                age_report = st.number_input(
                    'Age at Report',
                    value=patient.age_report,
                    min_value=0,
                    step=1,
                    key=f'{key_prefix}-age-report',
                )
            with unit_col:
                age_unit_options = [None] + [u.value for u in AgeUnit]
                age_report_current = (
                    patient.age_report_unit.value if patient.age_report_unit else None
                )
                age_report_idx = (
                    age_unit_options.index(age_report_current)
                    if age_report_current in age_unit_options
                    else 0
                )
                age_report_unit = st.selectbox(
                    'Unit',
                    options=age_unit_options,
                    index=age_report_idx,
                    key=f'{key_prefix}-age-report-unit',
                )
        with col2:
            st.space()
            age_report_note = render_evidence_controls(
                paper_resp.id,
                block=patient.age_report_evidence,
                label='Age at Report Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-agereport-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agereport-evidence',
                human_edit_note_key=f'{key_prefix}-age-report-note',
            )
        col1, col2 = st.columns(2)
        with col1:
            age_col, unit_col = st.columns([2, 1])
            with age_col:
                age_death = st.number_input(
                    'Age at Death',
                    value=patient.age_death,
                    min_value=0,
                    step=1,
                    key=f'{key_prefix}-age-death',
                )
            with unit_col:
                age_unit_options = [None] + [u.value for u in AgeUnit]
                age_death_current = (
                    patient.age_death_unit.value if patient.age_death_unit else None
                )
                age_death_idx = (
                    age_unit_options.index(age_death_current)
                    if age_death_current in age_unit_options
                    else 0
                )
                age_death_unit = st.selectbox(
                    'Unit',
                    options=age_unit_options,
                    index=age_death_idx,
                    key=f'{key_prefix}-age-death-unit',
                )
        with col2:
            st.space()
            age_death_note = render_evidence_controls(
                paper_resp.id,
                block=patient.age_death_evidence,
                label='Age at Death Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-agedeath-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-agedeath-evidence',
                human_edit_note_key=f'{key_prefix}-age-death-note',
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
            country_of_origin_note = render_evidence_controls(
                paper_resp.id,
                block=patient.country_of_origin_evidence,
                label='Country of Origin Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-country-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-country-evidence',
                human_edit_note_key=f'{key_prefix}-country-note',
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
            race_ethnicity_note = render_evidence_controls(
                paper_resp.id,
                block=patient.race_ethnicity_evidence,
                label='Race/Ethnicity Evidence',
                color_key=f'{key_prefix}-{patient.identifier}-color-race-evidence',
                button_key_prefix=f'{key_prefix}-{patient.identifier}-race-evidence',
                human_edit_note_key=f'{key_prefix}-race-note',
            )

        # --- Segregation Analysis (for LOD scoring)
        with st.expander('Segregation Analysis (for LOD Scoring)', expanded=False):
            # --- Is Obligate Carrier
            col1, col2 = st.columns(2)
            with col1:
                is_obligate_carrier = st.checkbox(
                    'Is Obligate Carrier',
                    value=patient.is_obligate_carrier or False,
                    key=f'{key_prefix}-obligate-carrier',
                )
            with col2:
                st.space()
                is_obligate_carrier_note = render_evidence_controls(
                    paper_resp.id,
                    block=patient.is_obligate_carrier_evidence,
                    label='Is Obligate Carrier Evidence',
                    color_key=f'{key_prefix}-{patient.identifier}-color-oc-evidence',
                    button_key_prefix=f'{key_prefix}-{patient.identifier}-oc-evidence',
                    human_edit_note_key=f'{key_prefix}-obligate-carrier-note',
                )

            # --- Relationship to Proband
            col1, col2 = st.columns(2)
            with col1:
                rel_options = [None] + [r.value for r in RelationshipToProband]
                rel_current = (
                    patient.relationship_to_proband.value
                    if patient.relationship_to_proband
                    else None
                )
                rel_idx = (
                    rel_options.index(rel_current) if rel_current in rel_options else 0
                )
                relationship_raw = st.selectbox(
                    'Relationship to Proband',
                    options=rel_options,
                    index=rel_idx,
                    key=f'{key_prefix}-relationship',
                )
                relationship_to_proband = (
                    RelationshipToProband(relationship_raw)
                    if relationship_raw
                    else None
                )
            with col2:
                st.space()
                relationship_note = render_evidence_controls(
                    paper_resp.id,
                    block=patient.relationship_to_proband_evidence,
                    label='Relationship to Proband Evidence',
                    color_key=f'{key_prefix}-{patient.identifier}-color-rel-evidence',
                    button_key_prefix=f'{key_prefix}-{patient.identifier}-rel-evidence',
                    human_edit_note_key=f'{key_prefix}-relationship-note',
                )

            # --- Twin Type
            col1, col2 = st.columns(2)
            with col1:
                twin_options = [None] + [t.value for t in TwinType]
                twin_current = patient.twin_type.value if patient.twin_type else None
                twin_idx = (
                    twin_options.index(twin_current)
                    if twin_current in twin_options
                    else 0
                )
                twin_raw = st.selectbox(
                    'Twin Type',
                    options=twin_options,
                    index=twin_idx,
                    key=f'{key_prefix}-twin-type',
                )
                twin_type = TwinType(twin_raw) if twin_raw else None
            with col2:
                st.space()
                twin_type_note = render_evidence_controls(
                    paper_resp.id,
                    block=patient.twin_type_evidence,
                    label='Twin Type Evidence',
                    color_key=f'{key_prefix}-{patient.identifier}-color-twin-evidence',
                    button_key_prefix=f'{key_prefix}-{patient.identifier}-twin-evidence',
                    human_edit_note_key=f'{key_prefix}-twin-type-note',
                )

        # --- Save edits: only include changed fields so exclude_unset works
        # Age fields are numeric (int or None). Convert 0 to None for empty values.
        age_diagnosis_val = age_diagnosis if age_diagnosis else None
        age_report_val = age_report if age_report else None
        age_death_val = age_death if age_death else None

        changes: dict[str, str | int | None] = {}
        if identifier != patient.identifier:
            changes['identifier'] = identifier
            # Set note to default if no existing note
            if not patient.identifier_evidence.human_edit_note:
                changes['identifier_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            identifier_note
            and identifier_note != patient.identifier_evidence.human_edit_note
        ):
            changes['identifier_human_edit_note'] = identifier_note

        if proband_status != patient.proband_status:
            changes['proband_status'] = proband_status.value
            if not patient.proband_status_evidence.human_edit_note:
                changes['proband_status_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            proband_status_note
            and proband_status_note != patient.proband_status_evidence.human_edit_note
        ):
            changes['proband_status_human_edit_note'] = proband_status_note

        if affected_status != patient.affected_status:
            changes['affected_status'] = affected_status.value
            if not patient.affected_status_evidence.human_edit_note:
                changes['affected_status_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            affected_status_note
            and affected_status_note != patient.affected_status_evidence.human_edit_note
        ):
            changes['affected_status_human_edit_note'] = affected_status_note

        if sex != patient.sex:
            changes['sex'] = sex.value
            if not patient.sex_evidence.human_edit_note:
                changes['sex_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if sex_note and sex_note != patient.sex_evidence.human_edit_note:
            changes['sex_human_edit_note'] = sex_note

        if age_diagnosis_val != patient.age_diagnosis:
            changes['age_diagnosis'] = age_diagnosis_val
            if not patient.age_diagnosis_evidence.human_edit_note:
                changes['age_diagnosis_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            age_diagnosis_note
            and age_diagnosis_note != patient.age_diagnosis_evidence.human_edit_note
        ):
            changes['age_diagnosis_human_edit_note'] = age_diagnosis_note

        age_diagnosis_current_unit = (
            patient.age_diagnosis_unit.value if patient.age_diagnosis_unit else None
        )
        if age_diagnosis_unit != age_diagnosis_current_unit:
            changes['age_diagnosis_unit'] = age_diagnosis_unit

        if age_report_val != patient.age_report:
            changes['age_report'] = age_report_val
            if not patient.age_report_evidence.human_edit_note:
                changes['age_report_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            age_report_note
            and age_report_note != patient.age_report_evidence.human_edit_note
        ):
            changes['age_report_human_edit_note'] = age_report_note

        age_report_current_unit = (
            patient.age_report_unit.value if patient.age_report_unit else None
        )
        if age_report_unit != age_report_current_unit:
            changes['age_report_unit'] = age_report_unit

        if age_death_val != patient.age_death:
            changes['age_death'] = age_death_val
            if not patient.age_death_evidence.human_edit_note:
                changes['age_death_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            age_death_note
            and age_death_note != patient.age_death_evidence.human_edit_note
        ):
            changes['age_death_human_edit_note'] = age_death_note

        age_death_current_unit = (
            patient.age_death_unit.value if patient.age_death_unit else None
        )
        if age_death_unit != age_death_current_unit:
            changes['age_death_unit'] = age_death_unit

        if country_of_origin != patient.country_of_origin:
            changes['country_of_origin'] = country_of_origin.value
            if not patient.country_of_origin_evidence.human_edit_note:
                changes['country_of_origin_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            country_of_origin_note
            and country_of_origin_note
            != patient.country_of_origin_evidence.human_edit_note
        ):
            changes['country_of_origin_human_edit_note'] = country_of_origin_note

        if race_ethnicity != patient.race_ethnicity:
            changes['race_ethnicity'] = race_ethnicity.value
            if not patient.race_ethnicity_evidence.human_edit_note:
                changes['race_ethnicity_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if (
            race_ethnicity_note
            and race_ethnicity_note != patient.race_ethnicity_evidence.human_edit_note
        ):
            changes['race_ethnicity_human_edit_note'] = race_ethnicity_note

        if is_obligate_carrier != (patient.is_obligate_carrier or False):
            changes['is_obligate_carrier'] = is_obligate_carrier
            if (
                patient.is_obligate_carrier_evidence
                and not patient.is_obligate_carrier_evidence.human_edit_note
            ):
                changes['is_obligate_carrier_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if is_obligate_carrier_note and (
            not patient.is_obligate_carrier_evidence
            or is_obligate_carrier_note
            != patient.is_obligate_carrier_evidence.human_edit_note
        ):
            changes['is_obligate_carrier_human_edit_note'] = is_obligate_carrier_note

        if relationship_to_proband != patient.relationship_to_proband:
            changes['relationship_to_proband'] = (
                relationship_to_proband.value if relationship_to_proband else None
            )
            if (
                patient.relationship_to_proband_evidence
                and not patient.relationship_to_proband_evidence.human_edit_note
            ):
                changes['relationship_to_proband_human_edit_note'] = (
                    HUMAN_EDIT_NOTE_DEFAULT
                )
        if relationship_note and (
            not patient.relationship_to_proband_evidence
            or relationship_note
            != patient.relationship_to_proband_evidence.human_edit_note
        ):
            changes['relationship_to_proband_human_edit_note'] = relationship_note

        if twin_type != patient.twin_type:
            changes['twin_type'] = twin_type.value if twin_type else None
            if (
                patient.twin_type_evidence
                and not patient.twin_type_evidence.human_edit_note
            ):
                changes['twin_type_human_edit_note'] = HUMAN_EDIT_NOTE_DEFAULT
        if twin_type_note and (
            not patient.twin_type_evidence
            or twin_type_note != patient.twin_type_evidence.human_edit_note
        ):
            changes['twin_type_human_edit_note'] = twin_type_note

        update_request = PatientUpdateRequest(**changes)  # type: ignore[arg-type]

        if changes:
            try:
                updated = update_patient(paper_resp.id, patient.id, update_request)
                # Update patients in session_state
                if PATIENTS_KEY in st.session_state:
                    patients_list: list[PatientResp] = st.session_state[PATIENTS_KEY]
                    for i, p in enumerate(patients_list):
                        if p.id == updated.id:
                            patients_list[i] = updated
                            st.session_state[PATIENTS_KEY] = patients_list
                            break
                st.toast('Saved!', icon=':material/check:')
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.toast(f'Failed to save: {str(e)}', icon='❌')

        # --- Phenotypes Section
        st.divider()
        st.markdown('### Phenotypes')
        try:
            phenotypes = get_phenotypes(paper_resp.id, patient.id)
            _render_patient_phenotypes(phenotypes, paper_resp, key_prefix, patient.id)
        except Exception as e:
            st.error(f'Failed to load phenotypes: {str(e)}')


def render_patients_tab(selected_patient_id: int | None) -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    if not paper_resp.title:
        st.write(f'{paper_resp.filename} not yet extracted...')
        return
    if not is_task_completed(paper_resp.tasks, TaskType.PATIENT_EXTRACTION):
        st.write(f'Patient Extraction not yet completed...')
        return
    # -----------------------------
    # Load patients
    # ---------------
    if PATIENTS_KEY not in st.session_state:
        st.session_state[PATIENTS_KEY] = get_patients(paper_resp.id)
    patients: list[PatientResp] = st.session_state[PATIENTS_KEY]

    # Load pedigree description
    pedigree_description = get_pedigree(paper_resp.id)

    # -----------------------------
    # Display Patients
    # -----------------------------
    indexed_patients = [(p.id, p) for p in patients]
    probands = [
        (patient_id, p)
        for patient_id, p in indexed_patients
        if p.proband_status == ProbandStatus.Proband
    ]
    non_probands = [
        (patient_id, p)
        for patient_id, p in indexed_patients
        if p.proband_status != ProbandStatus.Proband
    ]
    affecteds = [
        (patient_id, p)
        for patient_id, p in indexed_patients
        if p.affected_status == AffectedStatus.Affected
    ]
    unaffecteds = [
        (patient_id, p)
        for patient_id, p in indexed_patients
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
    # Load families
    if FAMILIES_KEY not in st.session_state:
        st.session_state[FAMILIES_KEY] = get_families(paper_resp.id)
    families: list[FamilyResp] = st.session_state[FAMILIES_KEY]

    with proband_tab:
        if not probands:
            st.info('No probands detected.')
        else:
            _render_patients_grouped_by_family(
                paper_resp, families, probands, selected_patient_id, 'patient-proband'
            )
    with non_proband_tab:
        if not non_probands:
            st.info('No non-probands detected.')
        else:
            _render_patients_grouped_by_family(
                paper_resp,
                families,
                non_probands,
                selected_patient_id,
                'patient-non-proband',
            )
    with affecteds_tab:
        if not affecteds:
            st.info('No affected patients detected.')
        else:
            _render_patients_grouped_by_family(
                paper_resp, families, affecteds, selected_patient_id, 'patient-affected'
            )
    with unaffecteds_tab:
        if not unaffecteds:
            st.info('No unaffected patients detected.')
        else:
            _render_patients_grouped_by_family(
                paper_resp,
                families,
                unaffecteds,
                selected_patient_id,
                'patient-unaffected',
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
