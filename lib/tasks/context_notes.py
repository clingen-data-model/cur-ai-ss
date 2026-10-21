"""A paper's additional context: the notes curators leave for the agents.

One list per paper (``PaperContextNoteDB``), read by every agent on every
run. Each note records where it came from and what it was about, so the
prompt can label it and a curator can take one out when it stops holding.
This module is the only writer, and renders the list for the prompts.
"""

from sqlalchemy.orm import Session

from lib.models.flag import FlagDB
from lib.models.paper_context_note import ContextNoteSource, PaperContextNoteDB
from lib.models.variant import VariantDB, get_variant_description

# How a note's anchor joins its parts, and what a note with no anchor says.
ANCHOR_SEP = ' · '
EVERY_TASK = 'All tasks'


def _variant_label(variant: VariantDB) -> str:
    return get_variant_description(
        variant.id, variant.harmonized_variant, variant.variant_evidence or {}
    )


def scope_label(
    session: Session,
    *,
    family_id: int | None = None,
    patient_id: int | None = None,
    variant_id: int | None = None,
    phenotype_id: int | None = None,
    patient_variant_occurrence_id: int | None = None,
) -> str | None:
    """The row a scoped run is for, as the label a reader knows it by
    ("patient P85", "variant c.511A>T"), or None for a paper-wide run."""
    from lib.models.family import FamilyDB
    from lib.models.patient import PatientDB
    from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB
    from lib.models.phenotype import PhenotypeDB

    parts: list[str] = []
    if family_id is not None and (family := session.get(FamilyDB, family_id)):
        parts.append(f'family {family.identifier}')
    if patient_id is not None and (patient := session.get(PatientDB, patient_id)):
        parts.append(f'patient {patient.identifier}')
    if variant_id is not None and (variant := session.get(VariantDB, variant_id)):
        parts.append(f'variant {_variant_label(variant)}')
    if phenotype_id is not None and (
        phenotype := session.get(PhenotypeDB, phenotype_id)
    ):
        parts.append(f'phenotype {phenotype.concept}')
    if patient_variant_occurrence_id is not None and (
        occurrence := session.get(
            PatientVariantOccurrenceDB, patient_variant_occurrence_id
        )
    ):
        parts.append(
            f'patient {occurrence.patient.identifier}, '
            f'variant {_variant_label(occurrence.variant)}'
        )
    return ', '.join(parts) or None


def flag_scope_label(flag: FlagDB) -> str | None:
    """``scope_label`` for the rows a flag links."""
    parts: list[str] = []
    if flag.family is not None:
        parts.append(f'family {flag.family.identifier}')
    if flag.patient is not None:
        parts.append(f'patient {flag.patient.identifier}')
    if flag.variant is not None:
        parts.append(f'variant {_variant_label(flag.variant)}')
    elif flag.occurrence is not None:
        parts.append(f'variant {_variant_label(flag.occurrence.variant)}')
    if flag.phenotype is not None:
        parts.append(f'phenotype {flag.phenotype.concept}')
    return ', '.join(parts) or None


def anchor_for(step: str, scope: str | None = None, flag: FlagDB | None = None) -> str:
    """A note's anchor: the step, the row if any, the flag's subject if any."""
    parts = [step]
    if scope:
        parts.append(scope)
    if flag is not None:
        parts.append(f'flag "{flag.subject}"')
    return ANCHOR_SEP.join(parts)


def add_context_note(
    session: Session,
    paper_id: int,
    text: str | None,
    *,
    source: ContextNoteSource,
    anchor: str | None = None,
    flag_id: int | None = None,
    user_id: int | None = None,
) -> PaperContextNoteDB | None:
    """Add a note to the paper's context; None when ``text`` is blank. A note
    for a flag replaces the one that flag's last re-run left, so re-running
    a flag with a better note does not stack the two."""
    if text is None or not text.strip():
        return None
    if flag_id is not None:
        session.query(PaperContextNoteDB).filter(
            PaperContextNoteDB.paper_id == paper_id,
            PaperContextNoteDB.flag_id == flag_id,
        ).delete()
    note = PaperContextNoteDB(
        paper_id=paper_id,
        text=text.strip(),
        source=source.value,
        anchor=anchor,
        flag_id=flag_id,
        created_by_user_id=user_id,
    )
    session.add(note)
    session.flush()
    return note


def render_context_notes(notes: list[PaperContextNoteDB]) -> str | None:
    """The notes as the prompt shows them: numbered, each led by its anchor
    in brackets, so an agent can tell which step or row a note is for. None
    when there are none."""
    if not notes:
        return None
    return '\n\n'.join(
        f'{n}. [{note.anchor or EVERY_TASK}] {note.text}'
        for n, note in enumerate(notes, start=1)
    )
