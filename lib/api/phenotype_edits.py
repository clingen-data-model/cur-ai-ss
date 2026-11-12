"""A curator's direct edits to phenotypes, shared by the API's phenotype
endpoints and the paper chat's Apply button, so a change made either way is
the same change: validated the same, attributed to the curator, and written
to the edit history.

Each function writes to the session and flushes; the caller commits and
touches the paper. A problem the curator can fix (an unknown individual,
phenotype or HPO id) raises ``EditError`` with the HTTP status the
endpoint answers with.
"""

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from lib.api.entity_edits import EditError, find_individual
from lib.models import HpoDB, PatientDB, PhenotypeDB
from lib.models.base import manual_evidence_block
from lib.models.deletion_log import record_deletion
from lib.models.edit import record_edit, record_edits
from lib.models.user import UserDB
from lib.reference_data.hpo import get_ontology


def hpo_name(hpo_id: str) -> str:
    """The term's name, or a 400 for an id the ontology does not have."""
    name = get_ontology().get_term_name(hpo_id)
    if name is None:
        raise EditError(400, f'Unknown HPO id: {hpo_id}')
    return name


def find_phenotype(session: Session, paper_id: int, phenotype_id: int) -> PhenotypeDB:
    phenotype = (
        session.query(PhenotypeDB)
        .options(joinedload(PhenotypeDB.hpo))
        .filter(PhenotypeDB.id == phenotype_id, PhenotypeDB.paper_id == paper_id)
        .one_or_none()
    )
    if phenotype is None:
        raise EditError(404, 'Phenotype not found')
    return phenotype


def add_phenotype(
    session: Session,
    *,
    paper_id: int,
    patient_id: int,
    concept: str,
    hpo_id: str | None,
    editor: UserDB,
    evidence: dict[str, Any] | None = None,
    hpo_note: str = 'Manually linked by curator',
) -> PhenotypeDB:
    """Add a phenotype row, linked to ``hpo_id`` when given. ``evidence`` is
    the concept's evidence block; a plain manual block when omitted (the
    form has no citation to give)."""
    find_individual(session, paper_id, patient_id)
    name = hpo_name(hpo_id) if hpo_id is not None else None

    phenotype = PhenotypeDB(
        paper_id=paper_id,
        patient_id=patient_id,
        concept=concept,
        concept_evidence=evidence or manual_evidence_block(concept),
        updated_by_user_id=editor.id,
    )
    session.add(phenotype)
    session.flush()
    record_edits(session, phenotype, ['concept'], editor)

    if hpo_id is not None:
        phenotype.hpo = HpoDB(hpo_id=hpo_id, hpo_name=name, reasoning=hpo_note)
        session.flush()  # hpo needs a real id before edits can reference it
        record_edits(session, phenotype.hpo, ['hpo'], editor)
    return phenotype


def remove_phenotype(
    session: Session, *, paper_id: int, phenotype_id: int, editor: UserDB
) -> str:
    """Delete a phenotype (its HPO link goes with it); the concept removed."""
    phenotype = find_phenotype(session, paper_id, phenotype_id)
    concept = phenotype.concept
    record_deletion(
        session,
        paper_id=phenotype.paper_id,
        entity_type='phenotype',
        entity_id=phenotype.id,
        identifier_snapshot=phenotype.concept,
        editor=editor,
    )
    session.delete(phenotype)
    session.flush()
    return concept


def relink_phenotype(
    session: Session,
    *,
    paper_id: int,
    phenotype_id: int,
    hpo_id: str | None,
    editor: UserDB,
    note: str | None = None,
) -> PhenotypeDB:
    """Link a phenotype to ``hpo_id``, or clear its link with None. ``note``
    replaces the default 'Manually linked/Unlinked by curator' reasoning."""
    phenotype = find_phenotype(session, paper_id, phenotype_id)
    if hpo_id is None:
        name = None
        reasoning = note or 'Unlinked by curator'
    else:
        name = hpo_name(hpo_id)
        reasoning = note or 'Manually linked by curator'

    old_hpo_id = phenotype.hpo.hpo_id if phenotype.hpo else None
    if phenotype.hpo:
        phenotype.hpo.hpo_id = hpo_id
        phenotype.hpo.hpo_name = name
        phenotype.hpo.reasoning = reasoning
    else:
        phenotype.hpo = HpoDB(hpo_id=hpo_id, hpo_name=name, reasoning=reasoning)
        session.flush()  # hpo needs a real id before edits can reference it
    record_edit(session, phenotype.hpo, 'hpo', editor, old_value=old_hpo_id)
    phenotype.updated_by_user_id = editor.id
    phenotype.updated_at = func.now()
    session.flush()
    return phenotype
