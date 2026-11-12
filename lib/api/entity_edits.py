"""A curator's direct edits to individuals, families, variants and
occurrences, shared by the API's endpoints and the paper chat's Apply button
(lib.api.direct_edits), so a change made either way is the same change:
validated the same, attributed to the curator, and written to the edit
history. Phenotypes have their own module, lib.api.phenotype_edits, because
their HPO link is a second row.

Updates need nothing here beyond ``update_variant``: every other entity's
``*UpdateRequest.apply_to`` already is the shared code.

Each function writes to the session and flushes; the caller commits and
touches the paper. A problem the curator can fix raises ``EditError`` with
the HTTP status the endpoint answers with.
"""

from sqlalchemy.orm import Session, joinedload

from lib.models import (
    FamilyDB,
    PatientDB,
    PatientVariantOccurrenceDB,
    VariantDB,
)
from lib.models.base import manual_evidence_block
from lib.models.deletion_log import record_deletion
from lib.models.edit import record_edits
from lib.models.family import FamilyCreateRequest
from lib.models.patient import PatientCreateRequest
from lib.models.patient_variant_occurrences import (
    PatientVariantOccurrenceCreateRequest,
)
from lib.models.user import UserDB
from lib.models.variant import VariantCreateRequest, VariantUpdateRequest


class EditError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# --- lookups --------------------------------------------------------------------


def find_family(session: Session, paper_id: int, family_id: int) -> FamilyDB:
    family = session.get(FamilyDB, family_id)
    if family is None or family.paper_id != paper_id:
        raise EditError(404, 'Family not found')
    return family


def find_individual(session: Session, paper_id: int, patient_id: int) -> PatientDB:
    patient = session.get(PatientDB, patient_id)
    if patient is None or patient.paper_id != paper_id:
        raise EditError(404, 'Individual not found')
    return patient


def find_variant(session: Session, paper_id: int, variant_id: int) -> VariantDB:
    variant = (
        session.query(VariantDB)
        .options(
            joinedload(VariantDB.harmonized_variant),
            joinedload(VariantDB.annotated_variant),
        )
        .filter(VariantDB.id == variant_id, VariantDB.paper_id == paper_id)
        .one_or_none()
    )
    if variant is None:
        raise EditError(404, 'Variant not found')
    return variant


def find_occurrence(
    session: Session, paper_id: int, occurrence_id: int
) -> PatientVariantOccurrenceDB:
    occurrence = session.get(PatientVariantOccurrenceDB, occurrence_id)
    if occurrence is None or occurrence.paper_id != paper_id:
        raise EditError(404, 'Occurrence not found')
    return occurrence


# --- families -------------------------------------------------------------------

FAMILY_CREATED_FIELDS = ['identifier', 'consanguinity']


def add_family(
    session: Session, *, paper_id: int, request: FamilyCreateRequest, editor: UserDB
) -> FamilyDB:
    family = FamilyDB(
        paper_id=paper_id,
        identifier=request.identifier,
        identifier_evidence=manual_evidence_block(request.identifier),
        consanguinity=request.consanguinity,
        consanguinity_evidence=manual_evidence_block(request.consanguinity),
        updated_by_user_id=editor.id,
    )
    session.add(family)
    session.flush()
    record_edits(session, family, FAMILY_CREATED_FIELDS, editor)
    return family


def remove_family(
    session: Session, *, paper_id: int, family_id: int, editor: UserDB
) -> str:
    """Delete an empty family. A family with members is refused rather than
    taking them with it: its individuals are the curation, and removing them
    is a separate, deliberate edit each."""
    family = find_family(session, paper_id, family_id)
    if family.patients:
        raise EditError(
            409,
            f'{family.identifier} still has {len(family.patients)} '
            'individual(s); delete all individuals in the family first',
        )
    identifier = family.identifier
    record_deletion(
        session,
        paper_id=paper_id,
        entity_type='family',
        entity_id=family.id,
        identifier_snapshot=identifier,
        editor=editor,
    )
    session.delete(family)
    session.flush()
    return identifier


# --- individuals ----------------------------------------------------------------

PATIENT_CREATED_FIELDS = [
    'identifier',
    'proband_status',
    'affected_status',
    'sex',
    'country_of_origin',
    'race',
    'ethnicity',
    'ancestry',
    'age_diagnosis',
    'age_report',
    'age_death',
    'age_onset',
    'family_assignment',
]


def add_individual(
    session: Session, *, paper_id: int, request: PatientCreateRequest, editor: UserDB
) -> PatientDB:
    family = find_family(session, paper_id, request.family_id)
    patient = PatientDB(
        paper_id=paper_id,
        family_id=request.family_id,
        identifier=request.identifier,
        identifier_evidence=manual_evidence_block(request.identifier),
        proband_status=request.proband_status,
        proband_status_evidence=manual_evidence_block(request.proband_status),
        affected_status=request.affected_status,
        affected_status_evidence=manual_evidence_block(request.affected_status),
        sex=request.sex,
        sex_evidence=manual_evidence_block(request.sex),
        country_of_origin=request.country_of_origin,
        country_of_origin_evidence=manual_evidence_block(request.country_of_origin),
        race=request.race,
        race_evidence=manual_evidence_block(request.race),
        ethnicity=request.ethnicity,
        ethnicity_evidence=manual_evidence_block(request.ethnicity),
        ancestry=request.ancestry,
        ancestry_evidence=manual_evidence_block(request.ancestry),
        age_diagnosis=request.age_diagnosis,
        age_diagnosis_evidence=manual_evidence_block(request.age_diagnosis),
        age_diagnosis_unit=request.age_diagnosis_unit,
        age_report=request.age_report,
        age_report_evidence=manual_evidence_block(request.age_report),
        age_report_unit=request.age_report_unit,
        age_death=request.age_death,
        age_death_evidence=manual_evidence_block(request.age_death),
        age_death_unit=request.age_death_unit,
        age_onset=request.age_onset,
        age_onset_evidence=manual_evidence_block(request.age_onset),
        age_onset_unit=request.age_onset_unit,
        onset_category=request.onset_category,
        onset_category_evidence=manual_evidence_block(request.onset_category)
        if request.onset_category
        else None,
        is_obligate_carrier=request.is_obligate_carrier,
        relationship_to_proband=request.relationship_to_proband,
        twin_type=request.twin_type,
        family_assignment_evidence=manual_evidence_block(family.identifier),
        updated_by_user_id=editor.id,
        created_by_user_id=editor.id,
    )
    session.add(patient)
    session.flush()
    record_edits(session, patient, PATIENT_CREATED_FIELDS, editor)
    return patient


def remove_individual(
    session: Session, *, paper_id: int, patient_id: int, editor: UserDB
) -> str:
    """Delete an individual (cascades to their occurrences and phenotypes)."""
    patient = find_individual(session, paper_id, patient_id)
    identifier = patient.identifier
    record_deletion(
        session,
        paper_id=paper_id,
        entity_type='patient',
        entity_id=patient.id,
        identifier_snapshot=identifier,
        editor=editor,
    )
    session.delete(patient)
    session.flush()
    return identifier


# --- variants -------------------------------------------------------------------

VARIANT_CREATED_FIELDS = [
    'variant',
    'transcript',
    'protein_accession',
    'genomic_accession',
    'lrg_accession',
    'gene_accession',
    'genomic_coordinates',
    'genome_build',
    'rsid',
    'caid',
    'hgvs_c',
    'hgvs_p',
    'hgvs_g',
    'variant_type',
    'functional_evidence',
    'main_focus',
]


def add_variant(
    session: Session, *, paper_id: int, request: VariantCreateRequest, editor: UserDB
) -> VariantDB:
    """A raw (unharmonized) variant: every field of the request, each with a
    manual evidence block."""
    values = request.model_dump()
    columns = {field: values[field] for field in VARIANT_CREATED_FIELDS}
    evidence = {
        f'{field}_evidence': manual_evidence_block(value)
        for field, value in columns.items()
    }
    variant = VariantDB(
        paper_id=paper_id,
        **columns,
        **evidence,
        updated_by_user_id=editor.id,
        created_by_user_id=editor.id,
    )
    session.add(variant)
    session.flush()
    record_edits(session, variant, VARIANT_CREATED_FIELDS, editor)
    return variant


def update_variant(
    session: Session,
    *,
    paper_id: int,
    variant_id: int,
    request: VariantUpdateRequest,
    editor: UserDB,
) -> VariantDB:
    variant = find_variant(session, paper_id, variant_id)
    request.apply_to(variant, editor, session)
    # Editing any harmonized field invalidates the downstream enrichment row,
    # which was computed by key lookup from the pre-edit coordinates. Treat
    # all harmonized siblings uniformly so a future enrichment lookup added
    # for e.g. hgvs_p cannot silently produce stale annotations. The
    # LLM-generated reasoning on harmonized_variant is intentionally kept
    # intact: it remains the agent's explanation of its original choices,
    # and the curator's rationale belongs in human_edit_note fields.
    harmonized_update = (
        request.harmonized_variant
        if 'harmonized_variant' in request.model_fields_set
        else None
    )
    if harmonized_update is not None:
        if variant.harmonized_variant is None:
            raise EditError(409, 'Variant has not been harmonized by the server yet')
        harmonized_update.apply_to(variant.harmonized_variant, editor, session)
        # delete-orphan cascade removes the row
        variant.annotated_variant = None
    session.flush()
    return variant


def variant_text(variant: VariantDB) -> str:
    """How a curator names a variant: as the paper wrote it, else HGVS."""
    hv = variant.harmonized_variant
    return (
        variant.variant
        or variant.hgvs_c
        or (hv.hgvs_c if hv else None)
        or variant.hgvs_p
        or f'variant {variant.id}'
    )


def remove_variant(
    session: Session, *, paper_id: int, variant_id: int, editor: UserDB
) -> str:
    """Delete a variant (cascades to occurrences)."""
    variant = find_variant(session, paper_id, variant_id)
    record_deletion(
        session,
        paper_id=paper_id,
        entity_type='variant',
        entity_id=variant.id,
        identifier_snapshot=variant.variant or variant.hgvs_c,
        editor=editor,
    )
    text = variant_text(variant)
    session.delete(variant)
    session.flush()
    return text


# --- occurrences ----------------------------------------------------------------


def add_occurrence(
    session: Session,
    *,
    paper_id: int,
    request: PatientVariantOccurrenceCreateRequest,
    editor: UserDB,
) -> PatientVariantOccurrenceDB:
    find_individual(session, paper_id, request.patient_id)
    find_variant(session, paper_id, request.variant_id)
    occurrence = PatientVariantOccurrenceDB(
        paper_id=paper_id,
        patient_id=request.patient_id,
        variant_id=request.variant_id,
        zygosity=request.zygosity,
        zygosity_evidence=manual_evidence_block(request.zygosity),
        inheritance=request.inheritance,
        inheritance_evidence=manual_evidence_block(request.inheritance),
        variant_inheritance=request.variant_inheritance,
        variant_inheritance_evidence=manual_evidence_block(request.variant_inheritance),
        testing_methods=request.testing_methods,
        testing_methods_evidence=[
            manual_evidence_block(method) for method in request.testing_methods
        ],
        disease_name=request.disease_name,
        updated_by_user_id=editor.id,
        created_by_user_id=editor.id,
    )
    session.add(occurrence)
    session.flush()
    record_edits(
        session,
        occurrence,
        ['zygosity', 'inheritance', 'variant_inheritance']
        + (['testing_methods'] if request.testing_methods else []),
        editor,
    )
    return occurrence


def remove_occurrence(
    session: Session, *, paper_id: int, occurrence_id: int, editor: UserDB
) -> None:
    occurrence = find_occurrence(session, paper_id, occurrence_id)
    record_deletion(
        session,
        paper_id=paper_id,
        entity_type='occurrence',
        entity_id=occurrence.id,
        identifier_snapshot=(
            f'patient {occurrence.patient_id}, variant {occurrence.variant_id} '
            f'({occurrence.zygosity})'
        ),
        editor=editor,
    )
    session.delete(occurrence)
    session.flush()
