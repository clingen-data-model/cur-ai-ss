"""Persist a single-pass curation.

Kept out of handlers.py because it is mostly index resolution: the curation
agent refers to patients and variants by their position in its own response,
since the database ids the split pipeline hands its agents do not exist when a
paper is curated in one pass.
"""

import logging

from sqlalchemy.orm import Session

from lib.agents.one_shot_paper_extraction_agent import OneShotPaperExtraction
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
    patient_variant_occurrence_to_db,
    phenotype_to_db,
    segregation_evidence_to_db,
    variant_to_db,
)
from lib.models.segregation_analysis import SegregationEvidenceDB
from lib.tasks.models import SUPERSEDED_BY_PAPER_EXTRACTION, TaskDB

logger = logging.getLogger(__name__)


def _clear_previous_run(session: Session, paper_id: int, agent_run_id: int) -> None:
    """Make the task idempotent, mirroring the split handlers' delete-then-insert."""
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


def clear_superseded_tasks(session: Session, paper_id: int) -> int:
    """Drop this paper's rows for the task types PAPER_EXTRACTION replaced.

    Scoped to the one paper, on purpose: papers still curated by the old
    pipeline keep their history. Entity-scoped rows (per patient, per family)
    would mostly cascade away when their entities are replaced, but the
    paper-level ones would not, so both are removed explicitly rather than
    relying on the foreign keys.
    """
    deleted = (
        session.query(TaskDB)
        .filter(
            TaskDB.paper_id == paper_id,
            TaskDB.type.in_(SUPERSEDED_BY_PAPER_EXTRACTION),
        )
        .delete(synchronize_session=False)
    )
    if deleted:
        logger.info(
            f'Paper {paper_id}: removed {deleted} task rows superseded by '
            'single-pass extraction'
        )
    return deleted


def persist_curation(
    session: Session,
    paper_id: int,
    agent_run_id: int,
    curation: OneShotPaperExtraction,
) -> dict[str, int]:
    """Write a whole curation, returning what was stored for logging."""
    superseded = clear_superseded_tasks(session, paper_id)
    _clear_previous_run(session, paper_id, agent_run_id)

    paper = session.get(PaperDB, paper_id)
    if paper:
        curation.metadata.apply_to(paper)

    session.query(SegregationEvidenceDB).filter(
        SegregationEvidenceDB.family_id.in_(
            session.query(FamilyDB.id).filter(FamilyDB.paper_id == paper_id)
        )
    ).delete(synchronize_session=False)

    family_ids: dict[str, int] = {}
    segregations = 0
    for entry in curation.families:
        db_family = family_to_db(paper_id, agent_run_id, entry.family)
        session.add(db_family)
        session.flush()
        family_ids[entry.family.identifier.value] = db_family.id
        if entry.segregation is not None:
            session.add(segregation_evidence_to_db(db_family.id, entry.segregation))
            segregations += 1

    # Patients keep their list position so occurrences can resolve against it.
    patient_ids: list[int] = []
    for patient in curation.patients:
        db_patient = PatientDB(
            paper_id=paper_id,
            agent_run_id=agent_run_id,
            identifier=patient.identifier.value,
            identifier_evidence=patient.identifier.model_dump(),
            proband_status=patient.proband_status.value.value,
            proband_status_evidence=patient.proband_status.model_dump(),
            family_assignment_evidence=patient.family_identifier.model_dump(),
        )
        family_id = family_ids.get(patient.family_identifier.value)
        if family_id is None:
            # families is NOT NULL on patients, so a family named by a patient but
            # missing from the families list gets created rather than costing us
            # the patient.
            logger.warning(
                f'Paper {paper_id}: patient {patient.identifier.value} names family '
                f'{patient.family_identifier.value!r}, which was not in the families '
                'list; creating it'
            )
            fallback = FamilyDB(
                paper_id=paper_id,
                agent_run_id=agent_run_id,
                identifier=patient.family_identifier.value,
                identifier_evidence=patient.family_identifier.model_dump(),
                consanguinity=False,
                consanguinity_evidence=patient.family_identifier.model_dump(),
            )
            session.add(fallback)
            session.flush()
            family_id = fallback.id
            family_ids[patient.family_identifier.value] = family_id
        db_patient.family_id = family_id
        apply_patient_demographics(db_patient, patient.demographics)
        session.add(db_patient)
        session.flush()
        patient_ids.append(db_patient.id)

    phenotypes = 0
    for phenotype in curation.phenotypes:
        # patient_id is an index into curation.patients here, not a database id
        if not (0 <= phenotype.patient_id < len(patient_ids)):
            logger.warning(
                f'Paper {paper_id}: phenotype names patient_id '
                f'{phenotype.patient_id}, out of range; skipped'
            )
            continue
        db_phenotype = phenotype_to_db(paper_id, phenotype)
        db_phenotype.patient_id = patient_ids[phenotype.patient_id]
        session.add(db_phenotype)
        phenotypes += 1

    variant_ids: list[int] = []
    for variant in curation.variants:
        db_variant = variant_to_db(paper_id, variant, agent_run_id)
        session.add(db_variant)
        session.flush()
        variant_ids.append(db_variant.id)

    occurrence_rows: dict[tuple[int, int], PatientVariantOccurrenceDB] = {}
    occurrences = 0
    for occurrence in curation.occurrences:
        # patient_id / variant_id are indices into this response, not db ids
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

    # Compound het pairs are nested on the patient that carries them, and link
    # two of that patient's occurrence rows to each other.
    paired = 0
    for patient_index, patient in enumerate(curation.patients):
        for pair in patient.compound_het:
            a = occurrence_rows.get((patient_index, pair.variant_id_a))
            b = occurrence_rows.get((patient_index, pair.variant_id_b))
            if a is None or b is None:
                logger.warning(
                    f'Paper {paper_id}: compound het for patient index '
                    f'{patient_index} names variants {pair.variant_id_a}/'
                    f'{pair.variant_id_b} with no occurrence; skipped'
                )
                continue
            for first, second in ((a, b), (b, a)):
                first.paired_variant_link_id = second.id
                first.paired_variant_confidence = pair.confidence.value.value
                first.paired_variant_confidence_reasoning = pair.confidence.model_dump()
            paired += 1

    if curation.pedigree.found and curation.pedigree.description:
        session.add(
            PedigreeDB(
                paper_id=paper_id,
                image_id=curation.pedigree.image_id or 0,
                description=curation.pedigree.description,
            )
        )

    return {
        'families': len(family_ids),
        'patients': len(patient_ids),
        'phenotypes': phenotypes,
        'variants': len(variant_ids),
        'occurrences': occurrences,
        'compound_het_pairs': paired,
        'segregation_families': segregations,
        'superseded_tasks_removed': superseded,
    }
