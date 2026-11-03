"""The review walk's steps: a paper's rows grouped by family.

Curation checks a family's occurrences together: who in the family carries
which variant, with what zygosity and inheritance, against the pedigree
and the segregation. So the walk (GET /papers/{id}/review-cases, the SPA's
/papers/$id/review page) steps through families in the paper's order, each
step the family's members, their occurrences and variants, and the open
flags about any of them. Variants no occurrence links trail as one step,
and open flags that name no row at all as a last, paper-level step; both
are optional: there to look at, never to confirm, and the walk's "next"
and its progress count families alone.

The order is the paper's own and never moves: the walk's "next" is stable,
and the client skips confirmed steps itself. A confirm stamps the step's
occurrences (lib/models/signoff.py); the members, variants and family are
listed for display, not stamped.
"""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from typing import Sequence

from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from lib.models.family import FamilyDB
from lib.models.flag import FlagDB
from lib.models.patient import PatientDB
from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB
from lib.models.phenotype import PhenotypeDB
from lib.models.signoff import SignoffColumns
from lib.models.variant import VariantDB


class ReviewCaseKind(StrEnum):
    FAMILY = 'family'
    UNLINKED_VARIANTS = 'unlinked_variants'
    PAPER = 'paper'


class ReviewCaseResp(BaseModel):
    key: str
    kind: ReviewCaseKind
    label: str
    family_id: int | None = None
    patient_ids: list[int] = []
    # The rows the step stamps.
    occurrence_ids: list[int] = []
    variant_ids: list[int] = []
    family_ids: list[int] = []
    # Open flags about any of them (or, for the paper-level step, about
    # nothing extracted).
    flag_ids: list[int] = []
    # Every occurrence of the step is stamped (a family with none: at once;
    # the unlinked-variants and paper-level steps: never, nothing to stamp).
    confirmed: bool
    # Not a step the walk requires: the unlinked-variants and paper-level
    # steps, which a curator may skip.
    optional: bool = False


def _stamped(rows: Sequence[SignoffColumns]) -> bool:
    """Every row stamped; an empty list is vacuously confirmed."""
    return all(row.reviewed_at is not None for row in rows)


def build_review_cases(session: Session, paper_id: int) -> list[ReviewCaseResp]:
    families = (
        session.query(FamilyDB)
        .options(selectinload(FamilyDB.patients))
        .filter(FamilyDB.paper_id == paper_id)
        .order_by(FamilyDB.id)
        .all()
    )
    occurrences = (
        session.query(PatientVariantOccurrenceDB)
        .filter(PatientVariantOccurrenceDB.paper_id == paper_id)
        .order_by(PatientVariantOccurrenceDB.id)
        .all()
    )
    variants = {
        variant.id: variant
        for variant in session.query(VariantDB)
        .filter(VariantDB.paper_id == paper_id)
        .order_by(VariantDB.id)
        .all()
    }
    open_flags = (
        session.query(FlagDB)
        .filter(FlagDB.paper_id == paper_id, FlagDB.resolved_at.is_(None))
        .order_by(FlagDB.id)
        .all()
    )
    phenotype_patient = {
        pid: patient_id
        for pid, patient_id in session.query(PhenotypeDB.id, PhenotypeDB.patient_id)
        .filter(PhenotypeDB.paper_id == paper_id)
        .all()
    }

    occurrences_by_patient: dict[int, list[PatientVariantOccurrenceDB]] = defaultdict(
        list
    )
    for occurrence in occurrences:
        occurrences_by_patient[occurrence.patient_id].append(occurrence)

    def flags_about(
        patient_ids: set[int],
        occurrence_ids: set[int],
        variant_ids: set[int],
        family_ids: set[int],
    ) -> list[FlagDB]:
        found = []
        for flag in open_flags:
            linked_patient = flag.patient_id
            if linked_patient is None and flag.phenotype_id is not None:
                linked_patient = phenotype_patient.get(flag.phenotype_id)
            if (
                (linked_patient is not None and linked_patient in patient_ids)
                or (flag.occurrence_id in occurrence_ids)
                or (flag.paired_occurrence_id in occurrence_ids)
                or (flag.variant_id in variant_ids)
                or (flag.family_id in family_ids)
            ):
                found.append(flag)
        return found

    cases: list[ReviewCaseResp] = []
    claimed_flags: set[int] = set()

    for family in families:
        members: list[PatientDB] = sorted(
            family.patients, key=lambda patient: patient.id
        )
        family_occurrences = [
            occurrence
            for patient in members
            for occurrence in occurrences_by_patient.get(patient.id, [])
        ]
        family_variants: list[VariantDB] = []
        for occurrence in family_occurrences:
            variant = variants.get(occurrence.variant_id)
            if variant is not None and variant not in family_variants:
                family_variants.append(variant)
        flags = flags_about(
            {patient.id for patient in members},
            {occurrence.id for occurrence in family_occurrences},
            {variant.id for variant in family_variants},
            {family.id},
        )
        claimed_flags.update(flag.id for flag in flags)
        cases.append(
            ReviewCaseResp(
                key=f'family-{family.id}',
                kind=ReviewCaseKind.FAMILY,
                label=family.identifier,
                family_id=family.id,
                patient_ids=[patient.id for patient in members],
                occurrence_ids=[occurrence.id for occurrence in family_occurrences],
                variant_ids=[variant.id for variant in family_variants],
                family_ids=[family.id],
                flag_ids=[flag.id for flag in flags],
                confirmed=_stamped(family_occurrences),
            )
        )

    linked_variant_ids = {occurrence.variant_id for occurrence in occurrences}
    unlinked = [
        variant for vid, variant in variants.items() if vid not in linked_variant_ids
    ]
    if unlinked:
        flags = flags_about(set(), set(), {variant.id for variant in unlinked}, set())
        claimed_flags.update(flag.id for flag in flags)
        cases.append(
            ReviewCaseResp(
                key='variants',
                kind=ReviewCaseKind.UNLINKED_VARIANTS,
                label='Variants linked to no patient',
                variant_ids=[variant.id for variant in unlinked],
                flag_ids=[flag.id for flag in flags],
                confirmed=False,
                optional=True,
            )
        )

    paper_flags = [flag for flag in open_flags if flag.id not in claimed_flags]
    if paper_flags:
        cases.append(
            ReviewCaseResp(
                key='paper',
                kind=ReviewCaseKind.PAPER,
                label='Flags about the paper',
                flag_ids=[flag.id for flag in paper_flags],
                confirmed=False,
                optional=True,
            )
        )
    # An occurrence whose patient the family loop never saw (none today: every
    # patient has a family) would be invisible; assert the invariant cheaply.
    seen = {pid for case in cases for pid in case.patient_ids}
    for occurrence in occurrences:
        if occurrence.patient_id not in seen:
            raise RuntimeError(f'occurrence {occurrence.id} belongs to no review case')
    return cases
