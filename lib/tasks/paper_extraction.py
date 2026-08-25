"""Persist what each reading pass produced.

Each pass is its own task, so each writes only its own slice and clears only
that slice on a rerun. Everything a later pass refers to is a database row by
the time it runs, so passes are given real ids and hand them back -- there are
no positions to resolve. What remains is checking that an id came from the list
we supplied, since a model can still return one we never sent.
"""

import logging

from sqlalchemy.orm import Session

from lib.agents.paper_extraction import (
    Genotypes,
    PatientDetails,
    SegregationFindings,
)
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
from lib.models.paper import PaperClassification, PedigreeExtractionOutput
from lib.models.patient import PatientExtractionOutput
from lib.models.segregation_analysis import SegregationEvidenceDB
from lib.models.variant import Variant

logger = logging.getLogger(__name__)


def persist_pedigree(
    session: Session, paper_id: int, pedigree: PedigreeExtractionOutput
) -> dict[str, int]:
    session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).delete()
    if not (pedigree.found and pedigree.description):
        return {'pedigrees': 0}
    # image_id was chosen from the figures the parse step extracted, so it
    # indexes a file that exists rather than a number the model invented.
    session.add(
        PedigreeDB(
            paper_id=paper_id,
            image_id=pedigree.image_id or 0,
            description=pedigree.description,
        )
    )
    return {'pedigrees': 1}


def persist_classification(
    session: Session, paper_id: int, classification: PaperClassification
) -> dict[str, int]:
    """Paper-level fields; nothing is keyed to these, so nothing is cleared."""
    paper = session.get(PaperDB, paper_id)
    if paper:
        classification.apply_to(paper)
    return {'classified': 1 if paper else 0}


def persist_patients(
    session: Session,
    paper_id: int,
    agent_run_id: int,
    extraction: PatientExtractionOutput,
) -> dict[str, int]:
    """The roster the later passes are keyed to.

    Rerunning it replaces the patients and families those passes referred to, so
    their output goes too. The database does most of that itself: phenotypes,
    occurrences and segregation evidence all cascade from what is deleted here,
    as do the scoped task rows pointing at them.
    """
    session.query(SegregationEvidenceDB).filter(
        SegregationEvidenceDB.family_id.in_(
            session.query(FamilyDB.id).filter(FamilyDB.paper_id == paper_id)
        )
    ).delete(synchronize_session=False)
    session.query(PatientDB).filter(PatientDB.paper_id == paper_id).delete()
    session.query(FamilyDB).filter(FamilyDB.paper_id == paper_id).delete()
    session.flush()

    family_ids: dict[str, int] = {}
    for entry in extraction.families:
        db_family = family_to_db(paper_id, agent_run_id, entry.family)
        session.add(db_family)
        session.flush()
        family_ids[entry.family.identifier.value] = db_family.id

    patients = 0
    for identity in extraction.patients:
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
        db_patient.family_id = family_id
        db_patient.family_assignment_evidence = identity.family_identifier.model_dump()
        session.add(db_patient)
        patients += 1

    session.flush()
    return {'families': len(family_ids), 'patients': patients}


def persist_variants(
    session: Session, paper_id: int, agent_run_id: int, variants: list[Variant]
) -> dict[str, int]:
    """Rerunning this drops the occurrences keyed to the old variant rows."""
    session.query(VariantDB).filter(VariantDB.paper_id == paper_id).delete()
    session.flush()

    for variant in variants:
        session.add(variant_to_db(paper_id, variant, agent_run_id))
    session.flush()
    return {'variants': len(variants)}


def persist_details(
    session: Session, paper_id: int, details: PatientDetails
) -> dict[str, int]:
    """Demographics onto the patients, and their phenotypes."""
    session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == paper_id).delete()
    session.flush()

    described = 0
    phenotypes = 0
    for detail in details.patients:
        patient = session.get(PatientDB, detail.patient_id)
        if patient is None or patient.paper_id != paper_id:
            logger.warning(
                f'Paper {paper_id}: details returned for patient_id '
                f"{detail.patient_id}, which is not one of this paper's patients; "
                'skipped'
            )
            continue
        apply_patient_demographics(patient, detail.demographics)
        described += 1
        # Phenotypes are nested under their patient, so that is what binds them:
        # a phenotype's own patient_id disagreeing would otherwise be silent.
        for phenotype in detail.phenotypes:
            db_phenotype = phenotype_to_db(paper_id, phenotype)
            db_phenotype.patient_id = patient.id
            session.add(db_phenotype)
            phenotypes += 1

    return {'described': described, 'phenotypes': phenotypes}


def persist_genotypes(
    session: Session, paper_id: int, genotypes: Genotypes
) -> dict[str, int]:
    session.query(PatientVariantOccurrenceDB).filter(
        PatientVariantOccurrenceDB.paper_id == paper_id
    ).delete()
    session.flush()

    patient_ids = {
        row_id
        for (row_id,) in session.query(PatientDB.id).filter(
            PatientDB.paper_id == paper_id
        )
    }
    variant_ids = {
        row_id
        for (row_id,) in session.query(VariantDB.id).filter(
            VariantDB.paper_id == paper_id
        )
    }

    rows: dict[tuple[int, int], PatientVariantOccurrenceDB] = {}
    for occurrence in genotypes.occurrences:
        if occurrence.patient_id not in patient_ids:
            logger.warning(
                f'Paper {paper_id}: occurrence names patient_id '
                f'{occurrence.patient_id}, which was not in the list supplied; skipped'
            )
            continue
        if occurrence.variant_id not in variant_ids:
            logger.warning(
                f'Paper {paper_id}: occurrence names variant_id '
                f'{occurrence.variant_id}, which was not in the list supplied; skipped'
            )
            continue
        db_occurrence = patient_variant_occurrence_to_db(paper_id, occurrence)
        session.add(db_occurrence)
        session.flush()
        rows[(occurrence.patient_id, occurrence.variant_id)] = db_occurrence

    # A compound het pair links two of one patient's occurrence rows to each other.
    paired = 0
    for het in genotypes.compound_het:
        for pair in het.pairs:
            a = rows.get((het.patient_id, pair.variant_id_a))
            b = rows.get((het.patient_id, pair.variant_id_b))
            if a is None or b is None:
                logger.warning(
                    f'Paper {paper_id}: compound het for patient_id {het.patient_id} '
                    f'names variants {pair.variant_id_a}/{pair.variant_id_b} with no '
                    'occurrence; skipped'
                )
                continue
            for first, second in ((a, b), (b, a)):
                first.paired_variant_link_id = second.id
                first.paired_variant_confidence = pair.confidence.value.value
                first.paired_variant_confidence_reasoning = pair.confidence.model_dump()
            paired += 1

    return {'occurrences': len(rows), 'compound_het_pairs': paired}


def persist_segregation(
    session: Session, paper_id: int, findings: SegregationFindings
) -> dict[str, int]:
    family_ids = {
        row_id
        for (row_id,) in session.query(FamilyDB.id).filter(
            FamilyDB.paper_id == paper_id
        )
    }
    session.query(SegregationEvidenceDB).filter(
        SegregationEvidenceDB.family_id.in_(family_ids)
    ).delete(synchronize_session=False)
    session.flush()

    stored = 0
    for finding in findings.families:
        if finding.family_id not in family_ids:
            logger.warning(
                f'Paper {paper_id}: segregation names family_id {finding.family_id}, '
                'which was not in the list supplied; skipped'
            )
            continue
        session.add(segregation_evidence_to_db(finding.family_id, finding.evidence))
        stored += 1

    return {'segregation_families': stored}
