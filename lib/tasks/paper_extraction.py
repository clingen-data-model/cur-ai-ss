"""Persist what the extraction passes produced.

Mostly resolution: each pass refers to patients, variants and families by name
or by position in a list it was given, because none of them exist in the
database when the passes run. The mapping differs per pass, so each site says
which one it is using.
"""

import logging

from sqlalchemy.orm import Session

from lib.agents.paper_extraction import PaperExtraction
from lib.models import (
    FamilyDB,
    PaperDB,
    PatientDB,
    PatientVariantOccurrenceDB,
    PedigreeDB,
    PhenotypeDB,
    VariantDB,
)
from lib.models.converters import (
    apply_patient_demographics,
    family_to_db,
    patient_identity_to_db,
    patient_variant_occurrence_to_db,
    phenotype_to_db,
    segregation_evidence_to_db,
    variant_to_db,
)
from lib.models.segregation_analysis import SegregationEvidenceDB

logger = logging.getLogger(__name__)


def _clear_previous_run(session: Session, paper_id: int, agent_run_id: int) -> None:
    """Make the task idempotent: delete what this run produced, then re-insert."""
    session.query(SegregationEvidenceDB).filter(
        SegregationEvidenceDB.family_id.in_(
            session.query(FamilyDB.id).filter(FamilyDB.paper_id == paper_id)
        )
    ).delete(synchronize_session=False)
    session.query(PatientVariantOccurrenceDB).filter(
        PatientVariantOccurrenceDB.paper_id == paper_id
    ).delete()
    session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == paper_id).delete()
    session.query(VariantDB).filter(
        VariantDB.paper_id == paper_id, VariantDB.agent_run_id == agent_run_id
    ).delete()
    session.query(PatientDB).filter(
        PatientDB.paper_id == paper_id, PatientDB.agent_run_id == agent_run_id
    ).delete()
    session.query(FamilyDB).filter(
        FamilyDB.paper_id == paper_id, FamilyDB.agent_run_id == agent_run_id
    ).delete()
    session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).delete()
    session.flush()


def persist_extraction(
    session: Session,
    paper_id: int,
    agent_run_id: int,
    extraction: PaperExtraction,
) -> dict[str, int]:
    """Write a whole extraction, returning what was stored for logging."""
    _clear_previous_run(session, paper_id, agent_run_id)

    paper = session.get(PaperDB, paper_id)
    if paper:
        extraction.classification.apply_to(paper)

    # Families keep the order pass 1 returned them in: pass 4 refers to that order.
    family_ids: dict[str, int] = {}
    family_order: list[int] = []
    for entry in extraction.patients.families:
        db_family = family_to_db(paper_id, agent_run_id, entry.family)
        session.add(db_family)
        session.flush()
        family_ids[entry.family.identifier.value] = db_family.id
        family_order.append(db_family.id)

    # Patients likewise: pass 3 refers to them by position in this list.
    patient_ids: list[int] = []
    patient_by_identifier: dict[str, PatientDB] = {}
    for identity in extraction.patients.patients:
        db_patient = patient_identity_to_db(paper_id, identity, agent_run_id)
        family_id = family_ids.get(identity.family_identifier.value)
        if family_id is None:
            # patients.family_id is NOT NULL, so a family named by a patient but
            # missing from the families list gets created rather than costing us
            # the patient.
            logger.warning(
                f'Paper {paper_id}: patient {identity.identifier.value} names family '
                f'{identity.family_identifier.value!r}, which was not returned; '
                'creating it'
            )
            fallback = FamilyDB(
                paper_id=paper_id,
                agent_run_id=agent_run_id,
                identifier=identity.family_identifier.value,
                identifier_evidence=identity.family_identifier.model_dump(),
                consanguinity=False,
                consanguinity_evidence=identity.family_identifier.model_dump(),
            )
            session.add(fallback)
            session.flush()
            family_id = fallback.id
            family_ids[identity.family_identifier.value] = family_id
            family_order.append(family_id)
        db_patient.family_id = family_id
        db_patient.family_assignment_evidence = identity.family_identifier.model_dump()
        session.add(db_patient)
        session.flush()
        patient_ids.append(db_patient.id)
        patient_by_identifier[identity.identifier.value] = db_patient

    # Pass 2 was given the identifiers rather than positions, so it keys by name.
    described = 0
    detail_owners: list[PatientDB | None] = []
    for detail in extraction.details.patients:
        detail_owner = patient_by_identifier.get(detail.identifier)
        detail_owners.append(detail_owner)
        if detail_owner is None:
            logger.warning(
                f'Paper {paper_id}: demographics returned for {detail.identifier!r}, '
                'who is not among the identified patients; skipped'
            )
            continue
        apply_patient_demographics(detail_owner, detail.demographics)
        described += 1

    # Phenotypes hang off the patient they were returned under, so their
    # patient_id field is not consulted: the nesting is the more reliable of the
    # two, and a mismatch between them would otherwise be silent.
    phenotypes = 0
    for index, detail in enumerate(extraction.details.patients):
        owner = detail_owners[index]
        if owner is None:
            continue
        for phenotype in detail.phenotypes:
            db_phenotype = phenotype_to_db(paper_id, phenotype)
            db_phenotype.patient_id = owner.id
            session.add(db_phenotype)
            phenotypes += 1

    variant_ids: list[int] = []
    for variant in extraction.variants:
        db_variant = variant_to_db(paper_id, variant, agent_run_id)
        session.add(db_variant)
        session.flush()
        variant_ids.append(db_variant.id)

    # Pass 3 was handed patients and variants as numbered lists; its patient_id
    # and variant_id are positions in those lists, not database ids.
    occurrence_rows: dict[tuple[int, int], PatientVariantOccurrenceDB] = {}
    occurrences = 0
    for occurrence in extraction.genotypes.occurrences:
        if not (0 <= occurrence.patient_id < len(patient_ids)):
            logger.warning(
                f'Paper {paper_id}: occurrence names patient index '
                f'{occurrence.patient_id}, out of range; skipped'
            )
            continue
        if not (0 <= occurrence.variant_id < len(variant_ids)):
            logger.warning(
                f'Paper {paper_id}: occurrence names variant index '
                f'{occurrence.variant_id}, out of range; skipped'
            )
            continue
        db_occurrence = patient_variant_occurrence_to_db(paper_id, occurrence)
        db_occurrence.patient_id = patient_ids[occurrence.patient_id]
        db_occurrence.variant_id = variant_ids[occurrence.variant_id]
        session.add(db_occurrence)
        session.flush()
        occurrence_rows[(occurrence.patient_id, occurrence.variant_id)] = db_occurrence
        occurrences += 1

    # A compound het pair links two of one patient's occurrence rows to each other.
    paired = 0
    for het in extraction.genotypes.compound_het:
        for pair in het.pairs:
            a = occurrence_rows.get((het.patient_index, pair.variant_id_a))
            b = occurrence_rows.get((het.patient_index, pair.variant_id_b))
            if a is None or b is None:
                logger.warning(
                    f'Paper {paper_id}: compound het for patient index '
                    f'{het.patient_index} names variants {pair.variant_id_a}/'
                    f'{pair.variant_id_b} with no occurrence; skipped'
                )
                continue
            for first, second in ((a, b), (b, a)):
                first.paired_variant_link_id = second.id
                first.paired_variant_confidence = pair.confidence.value.value
                first.paired_variant_confidence_reasoning = pair.confidence.model_dump()
            paired += 1

    segregations = 0
    for finding in extraction.segregation.families:
        if not (0 <= finding.family_index < len(family_order)):
            logger.warning(
                f'Paper {paper_id}: segregation names family index '
                f'{finding.family_index}, out of range; skipped'
            )
            continue
        session.add(
            segregation_evidence_to_db(
                family_order[finding.family_index], finding.evidence
            )
        )
        segregations += 1

    if extraction.pedigree.found and extraction.pedigree.description:
        # image_id was chosen from the figures the parse step extracted, so it
        # indexes a file that exists rather than a number the model invented.
        session.add(
            PedigreeDB(
                paper_id=paper_id,
                image_id=extraction.pedigree.image_id or 0,
                description=extraction.pedigree.description,
            )
        )

    return {
        'families': len(family_order),
        'patients': len(patient_ids),
        'described': described,
        'phenotypes': phenotypes,
        'variants': len(variant_ids),
        'occurrences': occurrences,
        'compound_het_pairs': paired,
        'segregation_families': segregations,
    }
