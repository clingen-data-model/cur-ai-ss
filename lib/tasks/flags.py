"""Persisting the flags an agent returns (see lib.models.flag).

Every handler does the same three things once its own rows are written:
delete the flags its agent raised last time, within the scope it ran in;
resolve each new flag's ``about`` to the rows it just wrote; insert. This
module is that, parameterised by the scope and the resolver, so each handler
contributes only the lookup it alone knows how to do.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from sqlalchemy.orm import Session

from lib.models.flag import LINK_COLUMNS, AnyFlag, FlagDB

# ``about`` -> the link columns it names, e.g. {'patient_id': 12}. Empty when
# nothing matches; the flag is still stored, just unlinked.
Resolver = Callable[[str], dict[str, int]]


def _norm(text: str | None) -> str:
    return ' '.join((text or '').split()).casefold()


def match_label(about: str, labels: Iterable[tuple[str | None, int]]) -> int | None:
    """The id whose label equals ``about`` after whitespace and case are
    ignored -- what an agent copying an identifier out of its own output
    or input can be relied on to preserve."""
    wanted = _norm(about)
    if not wanted:
        return None
    for label, row_id in labels:
        if _norm(label) == wanted:
            return row_id
    return None


def patient_labels_by_family(
    patients: Iterable[tuple[str, str, int]],
) -> list[tuple[str, int]]:
    """Labels an agent may write in ``about`` for each patient, as (label, id):
    the bare identifier when only one patient in the paper carries it, and
    always "family / identifier", since the family is not part of the
    identifier and two families may each have a "II-1" or a "sister"."""
    rows = list(patients)
    counts = Counter(_norm(identifier) for _, identifier, _ in rows)
    labels: list[tuple[str, int]] = []
    for family, identifier, row_id in rows:
        if counts[_norm(identifier)] == 1:
            labels.append((identifier, row_id))
        labels.append((f'{family} / {identifier}', row_id))
    return labels


def flags_of(output: Any) -> list[AnyFlag]:
    """The flags list of an agent output, or none: a fallback block built by
    a handler when the agent gave up, or an output from before flags
    existed, has no such attribute."""
    return list(getattr(output, 'flags', None) or [])


def split_pair(about: str) -> tuple[str, str] | None:
    """An ``about`` naming a patient-variant pair as "patient / variant"."""
    if ' / ' not in about:
        return None
    left, _, right = about.partition(' / ')
    return (left.strip(), right.strip()) if left.strip() and right.strip() else None


def replace_flags(
    session: Session,
    *,
    paper_id: int,
    source: str,
    flags: Sequence[AnyFlag],
    scope: dict[str, int] | None = None,
    resolve: Resolver | None = None,
) -> list[FlagDB]:
    """Replace ``source``'s flags for this run with ``flags``.

    ``scope`` is the row a per-entity task ran for ({'patient_id': 7} for a
    demographics or phenotype task, {'family_id': 3} for segregation): it
    bounds the delete, so one patient's re-run leaves the other patients'
    flags alone, and it is stamped on every new flag, so a flag that names
    nothing still lists under the patient it arose from. A paper-level task
    passes no scope and replaces all of its flags.

    ``resolve`` turns a flag's ``about`` into further link columns. A match
    adds to the scope rather than replacing it; a miss leaves the flag with
    the scope alone.
    """
    scope = dict(scope or {})
    for column in scope:
        assert column in LINK_COLUMNS, column

    # The app's sessions do not autoflush, and a bulk delete does not see
    # pending rows: flush first so a flag added earlier in this session is
    # replaced like one from a previous run.
    session.flush()
    query = session.query(FlagDB).filter(
        FlagDB.paper_id == paper_id, FlagDB.source == source
    )
    for column, value in scope.items():
        query = query.filter(getattr(FlagDB, column) == value)
    query.delete(synchronize_session=False)

    rows: list[FlagDB] = []
    for flag in flags:
        links: dict[str, Any] = dict(scope)
        if flag.about is not None and resolve is not None:
            links.update(resolve(flag.about))
        row = FlagDB(
            paper_id=paper_id,
            source=source,
            kind=flag.kind.value,
            subject=flag.flag.value,
            evidence=flag.flag.model_dump(),
            **links,
        )
        session.add(row)
        rows.append(row)
    return rows
