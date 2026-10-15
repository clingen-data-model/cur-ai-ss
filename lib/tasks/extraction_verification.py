"""Extraction verification: folding a paper's repeated flags into one.

The last task of a paper's pipeline (TaskType.EXTRACTION_VERIFICATION),
queued by the worker once every other task has settled, and run over every
open flag whatever agent raised it. The agent (lib.agents.
extraction_verification_agent) says which flags are one decision; this
module builds its input and applies its answer, and the handler in
lib.tasks.handlers runs the two around the model call:

- the earliest flag of each group survives, the rest are deleted, and the
  survivor's reasoning gains a line per absorbed flag naming the agent, the
  row and the subject, so nothing the model said is lost from view;
- the survivor keeps only the links the group agrees on. A decision that
  was flagged for the father and again for the mother is not about either
  of them: its patient link is cleared and, when they share a family, the
  family is linked instead. Two agents flagging the same patient keep that
  patient. A survivor that ends up with no scope row is a paper-level flag,
  and a per-patient re-run no longer deletes it (replace_flags bounds its
  delete by scope), so a merge survives the re-runs that follow it.

The agent's grouping is checked before it is applied -- ids must be open
flags of this paper, a flag in at most one group, two or more per group,
and not about different patient-variant links -- and a group that fails
stays unmerged.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from lib.models.flag import LINK_COLUMNS, FlagDB, FlagMergeOutput
from lib.models.variant import VariantDB, get_variant_description
from lib.tasks.models import TaskType

logger = logging.getLogger(__name__)

ALSO_RAISED = 'Also raised by'


def _variant_label(variant: VariantDB) -> str:
    return get_variant_description(
        variant.id, variant.harmonized_variant, variant.variant_evidence or {}
    )


def _about(flag: FlagDB) -> str | None:
    """The rows a flag links, as the labels a reader knows them by."""
    parts: list[str] = []
    if flag.family is not None:
        parts.append(f'family {flag.family.identifier}')
    if flag.patient is not None:
        parts.append(f'patient {flag.patient.identifier}')
    if flag.variant is not None:
        parts.append(f'variant {_variant_label(flag.variant)}')
    elif flag.occurrence is not None:
        parts.append(f'variant {_variant_label(flag.occurrence.variant)}')
    if flag.paired_occurrence is not None:
        parts.append(f'paired with {_variant_label(flag.paired_occurrence.variant)}')
    if flag.phenotype is not None:
        parts.append(f'phenotype {flag.phenotype.concept}')
    return ', '.join(parts) or None


def _agent_label(source: str) -> str:
    try:
        return TaskType[source].value
    except KeyError:
        return source


def open_flags(session: Session, paper_id: int) -> list[FlagDB]:
    return (
        session.query(FlagDB)
        .filter(FlagDB.paper_id == paper_id, FlagDB.resolved_at.is_(None))
        .order_by(FlagDB.id)
        .all()
    )


def verification_input(flags: list[FlagDB]) -> list[dict[str, Any]]:
    """The agent's view of the flags: everything a reader would use to tell
    two decisions apart, nothing that would let it match on bookkeeping."""
    return [
        {
            'id': f.id,
            'agent': _agent_label(f.source),
            'kind': f.kind,
            'about': _about(f),
            'subject': f.subject,
            'reasoning': (f.evidence or {}).get('reasoning', ''),
        }
        for f in flags
    ]


def _checked_groups(
    output: FlagMergeOutput, by_id: dict[int, FlagDB]
) -> list[list[FlagDB]]:
    """The agent's groups as rows, earliest first; a group with an unknown,
    resolved or already-used id, fewer than two flags, or flags about
    different patient-variant links, is skipped."""
    groups: list[list[FlagDB]] = []
    used: set[int] = set()
    for group in output.groups:
        ids = {group.keep, *group.merged}
        if len(ids) < 2:
            continue
        if not ids <= by_id.keys() or ids & used:
            logger.warning(
                'Flag merge group skipped, ids not all open and unused: %s', sorted(ids)
            )
            continue
        rows = sorted((by_id[i] for i in ids), key=lambda f: f.id)
        # A flag linked to a patient-variant link, or to a compound-het pair
        # of them, is about that row: the curator needs it there. Folding two
        # such flags about different links would clear the link and take the
        # indicator off both rows, so they stay apart. Flags about the same
        # link, or with none, merge as before.
        if len({(f.occurrence_id, f.paired_occurrence_id) for f in rows}) > 1 and any(
            f.occurrence_id is not None for f in rows
        ):
            logger.info(
                'Flag merge group kept apart, flags are about different links: %s',
                sorted(ids),
            )
            continue
        used |= ids
        groups.append(rows)
    return groups


def _covering_links(group: list[FlagDB]) -> dict[str, int | None]:
    """The links every flag in the group shares, with the family filled in
    when the patients differ but all belong to one."""
    links: dict[str, int | None] = {}
    for column in LINK_COLUMNS:
        values = {getattr(f, column) for f in group}
        links[column] = values.pop() if len(values) == 1 else None
    if links['patient_id'] is None and links['family_id'] is None:
        families = {f.patient.family_id for f in group if f.patient is not None}
        if len(families) == 1 and None not in families:
            links['family_id'] = families.pop()
    return links


def apply_merge(session: Session, paper_id: int, output: FlagMergeOutput) -> int:
    """Fold the agent's groups into their earliest flags; the number of flags
    absorbed. Safe to apply twice: the second pass finds the absorbed ids gone
    and skips their groups."""
    by_id = {f.id: f for f in open_flags(session, paper_id)}
    absorbed = 0
    for group in _checked_groups(output, by_id):
        survivor, *rest = group
        evidence = dict(survivor.evidence or {})
        reasoning = evidence.get('reasoning') or ''
        for flag in rest:
            about = _about(flag)
            note = (
                f'{ALSO_RAISED} {_agent_label(flag.source)}'
                f'{f" for {about}" if about else ""}: {flag.subject}.'
            )
            if note not in reasoning:
                reasoning = f'{reasoning}\n\n{note}' if reasoning else note
        evidence['reasoning'] = reasoning
        survivor.evidence = evidence
        for column, value in _covering_links(group).items():
            setattr(survivor, column, value)
        for flag in rest:
            session.delete(flag)
        absorbed += len(rest)
        logger.info(
            'Paper %s: flag %s absorbed %s (%s)',
            paper_id,
            survivor.id,
            [f.id for f in rest],
            survivor.subject,
        )
    session.flush()
    return absorbed
