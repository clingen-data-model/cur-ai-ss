"""Versioned on-disk snapshots of a paper's extracted database state.

A snapshot is one JSON file under ``<pdf_dir>/snapshots/`` holding a faithful
column dump of every paper-scoped table, written when the extraction pipeline
completes and right before a rerun is queued (so an edit or deletion made
between the two is never silently lost to the rerun's delete-and-recreate).
Restoring wipes the paper's domain rows -- tasks, edit history, and the
deletion log included -- and re-inserts them with their original primary
keys, so every snapshot is a self-consistent reality: entities, links, edit
history, deletions, and the task history that produced them, all as of
exactly that moment.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, Table, insert, or_, text, update
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from lib.agents.run_tracking import get_current_git_hash
from lib.core.environment import env
from lib.misc.pdf.paths import snapshots_dir
from lib.models import (
    AnnotatedVariantDB,
    Base,
    FamilyDB,
    HarmonizedVariantDB,
    HpoDB,
    PaperDB,
    PatientDB,
    PatientVariantOccurrenceDB,
    PedigreeDB,
    PhenotypeDB,
    SegregationAnalysisComputedDB,
    SegregationEvidenceDB,
    SnapshotDB,
    SnapshotMeta,
    TaskDB,
    UserDB,
    VariantDB,
)
from lib.models.base import row_to_dict
from lib.models.deletion_log import DeletionLogDB
from lib.models.edit import EditDB
from lib.tasks.models import TaskType

logger = logging.getLogger(__name__)

# Version 2: tasks are part of the snapshot (restored wholesale with the domain
# rows). Version-1 files predate that and cannot be restored safely -- doing so
# would delete the paper's task history and restore nothing in its place.
SNAPSHOT_FILE_VERSION = 2

_SNAPSHOT_NAME_RE = re.compile(r'^extraction_\d{8}T\d{12}Z\.json$')

# Parent-first: each table's FKs point only at tables earlier in the list
# (patient_variant_occurrences' self-FK is handled with a second pass).
_INSERT_ORDER: list[tuple[str, type[Base]]] = [
    ('families', FamilyDB),
    ('patients', PatientDB),
    ('pedigrees', PedigreeDB),
    ('phenotypes', PhenotypeDB),
    ('hpos', HpoDB),
    ('variants', VariantDB),
    ('harmonized_variants', HarmonizedVariantDB),
    ('annotated_variants', AnnotatedVariantDB),
    ('patient_variant_occurrences', PatientVariantOccurrenceDB),
    ('segregation_evidence', SegregationEvidenceDB),
    ('segregation_analysis_computed', SegregationAnalysisComputedDB),
    # Edit history and the deletion log version alongside the data they
    # describe -- every FK target above is already inserted by this point.
    # deletion_log has no FK of its own (see its docstring), so its position
    # here only matters relative to 'tasks'.
    ('edits', EditDB),
    ('deletion_log', DeletionLogDB),
    # Last: tasks FK every entity table above.
    ('tasks', TaskDB),
]

# Extracted/editable paper columns a reset restores. Identity and file
# bookkeeping (content_hash, gene_id, filename, supplement_format) stay put.
_PAPER_RESTORE_COLUMNS = (
    'title',
    'first_author',
    'journal_name',
    'abstract',
    'publication_year',
    'doi',
    'pmid',
    'pmcid',
    'paper_types',
    'tags',
    'is_paper_relevant',
    'section_classifications',
    'disease_name',
    'disease_name_evidence',
    'disease_inheritance_mode',
    'disease_inheritance_mode_evidence',
    'mondo_id',
    'mondo_term',
    'mondo_match_context',
)

# Attribution and task-bookkeeping columns churn on every run without
# representing extraction output, so they don't participate in change
# detection (they are still stored in and restored from the snapshot).
_HASH_EXCLUDED_KEYS = {
    'updated_at',
    'updated_by_user_id',
    'tries',
    'error_message',
    'edited_at',
    'deleted_at',
}


def _paper_edit_filter(
    paper_id: int,
    *,
    family_ids: list[int],
    patient_ids: list[int],
    variant_ids: list[int],
    occurrence_ids: list[int],
    segregation_evidence_ids: list[int],
) -> Any:
    """Every EditDB row reachable from this paper, across its six mutually
    exclusive entity-FK columns (see EditDB's _ENTITY_FK_COLUMNS)."""
    clauses = [EditDB.paper_id == paper_id]
    if family_ids:
        clauses.append(EditDB.family_id.in_(family_ids))
    if patient_ids:
        clauses.append(EditDB.patient_id.in_(patient_ids))
    if variant_ids:
        clauses.append(EditDB.variant_id.in_(variant_ids))
    if occurrence_ids:
        clauses.append(EditDB.occurrence_id.in_(occurrence_ids))
    if segregation_evidence_ids:
        clauses.append(EditDB.segregation_evidence_id.in_(segregation_evidence_ids))
    return or_(*clauses)


def _model_table(model: type[Base]) -> Table:
    table = model.__table__
    assert isinstance(table, Table)
    return table


class InvalidSnapshotNameError(ValueError):
    pass


class SnapshotNotFoundError(FileNotFoundError):
    pass


class SnapshotIncompatibleError(RuntimeError):
    pass


def snapshot_path(paper_id: int, name: str) -> Path:
    if not _SNAPSHOT_NAME_RE.match(name):
        raise InvalidSnapshotNameError(f'Invalid snapshot name: {name!r}')
    return snapshots_dir(paper_id) / name


def snapshot_file_paths(paper_id: int) -> list[Path]:
    """Every on-disk snapshot file for a paper, unsorted.

    For indexing/backfill use only -- list_snapshots() is the fast, DB-backed
    path normal reads should use."""
    directory = snapshots_dir(paper_id)
    if not directory.exists():
        return []
    return [
        path
        for path in directory.glob('extraction_*.json')
        if _SNAPSHOT_NAME_RE.match(path.name)
    ]


def dump_paper_state(paper_id: int, paper_db: PaperDB, session: Session) -> dict:
    """Dump every paper-scoped table to a dict of raw column values."""
    families = session.query(FamilyDB).filter(FamilyDB.paper_id == paper_id).all()
    family_ids = [f.id for f in families]
    patients = session.query(PatientDB).filter(PatientDB.paper_id == paper_id).all()
    pedigrees = session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).all()
    phenotypes = (
        session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == paper_id).all()
    )
    phenotype_ids = [p.id for p in phenotypes]
    hpos = (
        session.query(HpoDB).filter(HpoDB.phenotype_id.in_(phenotype_ids)).all()
        if phenotype_ids
        else []
    )
    variants = session.query(VariantDB).filter(VariantDB.paper_id == paper_id).all()
    variant_ids = [v.id for v in variants]
    harmonized = (
        session.query(HarmonizedVariantDB)
        .filter(HarmonizedVariantDB.variant_id.in_(variant_ids))
        .all()
        if variant_ids
        else []
    )
    enriched = (
        session.query(AnnotatedVariantDB)
        .filter(AnnotatedVariantDB.variant_id.in_(variant_ids))
        .all()
        if variant_ids
        else []
    )
    pvlinks = (
        session.query(PatientVariantOccurrenceDB)
        .filter(PatientVariantOccurrenceDB.paper_id == paper_id)
        .all()
    )
    seg_evidence = (
        session.query(SegregationEvidenceDB)
        .filter(SegregationEvidenceDB.family_id.in_(family_ids))
        .all()
        if family_ids
        else []
    )
    seg_computed = (
        session.query(SegregationAnalysisComputedDB)
        .filter(SegregationAnalysisComputedDB.family_id.in_(family_ids))
        .all()
        if family_ids
        else []
    )
    tasks = session.query(TaskDB).filter(TaskDB.paper_id == paper_id).all()

    patient_ids = [p.id for p in patients]
    occurrence_ids = [o.id for o in pvlinks]
    segregation_evidence_ids = [s.id for s in seg_evidence]
    edits = (
        session.query(EditDB)
        .filter(
            _paper_edit_filter(
                paper_id,
                family_ids=family_ids,
                patient_ids=patient_ids,
                variant_ids=variant_ids,
                occurrence_ids=occurrence_ids,
                segregation_evidence_ids=segregation_evidence_ids,
            )
        )
        .all()
    )
    deletions = (
        session.query(DeletionLogDB).filter(DeletionLogDB.paper_id == paper_id).all()
    )

    return {
        'paper': row_to_dict(paper_db),
        'families': [row_to_dict(r) for r in families],
        'patients': [row_to_dict(r) for r in patients],
        'pedigrees': [row_to_dict(r) for r in pedigrees],
        'phenotypes': [row_to_dict(r) for r in phenotypes],
        'hpos': [row_to_dict(r) for r in hpos],
        'variants': [row_to_dict(r) for r in variants],
        'harmonized_variants': [row_to_dict(r) for r in harmonized],
        'annotated_variants': [row_to_dict(r) for r in enriched],
        'patient_variant_occurrences': [row_to_dict(r) for r in pvlinks],
        'segregation_evidence': [row_to_dict(r) for r in seg_evidence],
        'segregation_analysis_computed': [row_to_dict(r) for r in seg_computed],
        'edits': [row_to_dict(r) for r in edits],
        'deletion_log': [row_to_dict(r) for r in deletions],
        'tasks': [row_to_dict(r) for r in tasks],
    }


def _encode_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _encode_row(row: dict) -> dict:
    return {key: _encode_value(value) for key, value in row.items()}


def _encode_tables(state: dict) -> dict:
    return {
        key: _encode_row(value)
        if isinstance(value, dict)
        else [_encode_row(row) for row in value]
        for key, value in state.items()
    }


def _state_hash(encoded_tables: dict) -> str:
    def scrub(row: dict) -> dict:
        return {k: v for k, v in row.items() if k not in _HASH_EXCLUDED_KEYS}

    scrubbed = {
        key: scrub(value) if isinstance(value, dict) else [scrub(r) for r in value]
        for key, value in encoded_tables.items()
    }
    canonical = json.dumps(scrubbed, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _safe_git_hash() -> str | None:
    """Current git commit, or None where git or the repo is unavailable."""
    try:
        return get_current_git_hash()
    except Exception:
        return None


def current_state_hash(paper_id: int, paper_db: PaperDB, session: Session) -> str:
    """Hash of the paper's current extracted state, comparable to a snapshot's
    ``meta.state_hash``."""
    return _state_hash(_encode_tables(dump_paper_state(paper_id, paper_db, session)))


def _current_alembic_revision(session: Session) -> str | None:
    bind = session.get_bind()
    if not sa_inspect(bind).has_table('alembic_version'):
        return None
    return session.execute(text('SELECT version_num FROM alembic_version')).scalar()


def list_snapshots(paper_id: int, session: Session) -> list[SnapshotMeta]:
    """List every snapshot for a paper, newest first, from the snapshots index
    table -- an indexed query instead of json.loads()-ing every on-disk
    snapshot file (including its large `tables` blob) just for the `meta`
    block. The file remains the source of truth for restoring; a row whose
    file is missing (e.g. hand-deleted outside the app) is skipped rather
    than surfaced, since restoring to it would fail anyway. Only the file's
    existence is checked here (a cheap stat), never its contents."""
    rows = (
        session.query(SnapshotDB)
        .filter(SnapshotDB.paper_id == paper_id)
        .order_by(SnapshotDB.created_at.desc())
        .all()
    )
    metas: list[SnapshotMeta] = []
    for row in rows:
        if not snapshot_path(paper_id, row.name).exists():
            logger.warning('Skipping snapshot %s: file missing on disk', row.name)
            continue
        metas.append(
            SnapshotMeta(
                name=row.name,
                version=row.version,
                created_at=row.created_at,
                paper_id=row.paper_id,
                alembic_revision=row.alembic_revision,
                model=row.model,
                description=row.description,
                git_hash=row.git_hash,
                state_hash=row.state_hash,
            )
        )
    return metas


# tasks scope columns and the label used for them in snapshot descriptions
_SCOPE_LABELS = (
    ('family_id', 'family'),
    ('patient_id', 'patient'),
    ('variant_id', 'variant'),
    ('phenotype_id', 'phenotype'),
    ('patient_variant_occurrence_id', 'occurrence'),
)


def _snapshot_description(
    paper_id: int, session: Session, previous: SnapshotMeta | None
) -> str:
    """Heuristic label for what produced this snapshot.

    User actions stamp ``tasks.updated_by_user_id``, and enqueue_successors
    propagates that stamp down the whole cascade -- so within the current
    pipeline cycle (tasks updated since the previous snapshot) the task the
    user actually clicked is the stamped one that finished FIRST, not last.
    A terminal leaf like Segregation Analysis Computed always finishes last;
    ordering ascending keeps the label on the root (e.g. Patient Extraction)."""
    query = session.query(TaskDB).filter(
        TaskDB.paper_id == paper_id,
        TaskDB.updated_by_user_id.isnot(None),
    )
    if previous is not None:
        # Only this cycle's tasks. SQLite returns naive UTC datetimes, so the
        # aware snapshot timestamp is converted for the comparison.
        prev_created = previous.created_at.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.filter(TaskDB.updated_at > prev_created)
    root = query.order_by(TaskDB.updated_at.asc(), TaskDB.id.asc()).first()
    if root is None:
        return 'Pipeline run'
    if previous is None and root.type == TaskType.PDF_PARSING:
        return 'Initial extraction'
    scope = ', '.join(
        f'{label} {getattr(root, column)}'
        for column, label in _SCOPE_LABELS
        if getattr(root, column) is not None
    )
    return f'{root.type.value} re-run' + (f' ({scope})' if scope else '')


def write_snapshot(
    paper_id: int,
    session: Session,
    description: str | None = None,
) -> Path | None:
    """Write a new snapshot unless the latest one already matches current state."""
    paper_db = session.get(PaperDB, paper_id)
    if paper_db is None:
        return None

    encoded = _encode_tables(dump_paper_state(paper_id, paper_db, session))
    state_hash = _state_hash(encoded)
    existing = list_snapshots(paper_id, session)
    if existing and existing[0].state_hash == state_hash:
        return None

    previous = existing[0] if existing else None
    if description is None:
        description = _snapshot_description(paper_id, session, previous)

    now = datetime.now(timezone.utc)
    # Model and git hash come from the writing process's environment, not the
    # agent_runs table -- that table's rows are stale (a run row is only ever
    # created when the table is empty) and would mislabel every snapshot.
    meta = {
        'version': SNAPSHOT_FILE_VERSION,
        'created_at': now.isoformat(),
        'paper_id': paper_id,
        'alembic_revision': _current_alembic_revision(session),
        'model': env.EXTRACTION_MODEL,
        'git_hash': _safe_git_hash(),
        'state_hash': state_hash,
        'description': description,
    }

    name = f'extraction_{now:%Y%m%dT%H%M%S%f}Z.json'
    path = snapshot_path(paper_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix('.tmp')
    tmp_path.write_text(json.dumps({'meta': meta, 'tables': encoded}))
    os.replace(tmp_path, path)

    # The file write above is already atomic (temp file + rename) and is
    # complete by the time this index row is added, so the only possible
    # drift from a crash before the caller's transaction commits is an
    # orphan file with no row -- never a row pointing at a missing file.
    session.add(
        SnapshotDB(
            paper_id=paper_id,
            name=name,
            version=meta['version'],
            created_at=now,
            alembic_revision=meta['alembic_revision'],
            model=meta['model'],
            description=meta['description'],
            git_hash=meta['git_hash'],
            state_hash=state_hash,
        )
    )
    # Sessions here run with autoflush=False (worker.py, this module's own
    # callers), so without this, a second write_snapshot in the same session
    # -- or any other same-session read via list_snapshots -- would not see
    # this row and would treat the paper as having no snapshots yet.
    session.flush()
    logger.info('Wrote extraction snapshot %s for paper %s', name, paper_id)
    return path


def write_snapshot_safe(
    session: Session, paper_id: int, description: str | None = None
) -> Path | None:
    """write_snapshot, but a failure logs and returns None instead of raising.

    For call sites where a snapshot is a safety net around some other action
    (a rerun, a pipeline cycle finishing) rather than the point of the call --
    a snapshot failure must never fail the thing it's attached to."""
    try:
        return write_snapshot(paper_id, session, description=description)
    except Exception:
        logger.exception('Failed to write extraction snapshot for paper %s', paper_id)
        return None


def _coerce_value(column: Column, value: object) -> object:
    if value is None:
        return None
    if (
        isinstance(column.type, SQLEnum)
        and column.type.enum_class is not None
        and isinstance(value, str)
    ):
        return column.type.enum_class(value)
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _coerce_row(table: Table, row: dict) -> dict:
    """Filter a snapshot row to current columns and coerce JSON scalars back to
    Python values. Tolerates schema drift in both directions except a new
    NOT NULL column without a default, which cannot be filled from an old
    snapshot."""
    out: dict = {}
    for column in table.columns:
        if column.name in row:
            out[column.name] = _coerce_value(column, row[column.name])
        elif (
            not column.nullable
            and column.default is None
            and column.server_default is None
            and not column.primary_key
        ):
            raise SnapshotIncompatibleError(
                f'Snapshot predates a schema change: required column '
                f'{table.name}.{column.name} is missing. Take a new extraction '
                f'run before resetting to it.'
            )
    return out


def _delete_paper_domain_rows(session: Session, paper_id: int) -> None:
    """Bulk-delete the paper's domain rows child-first, tasks before the
    entities their scope FKs point at."""
    family_ids = [
        i for (i,) in session.query(FamilyDB.id).filter(FamilyDB.paper_id == paper_id)
    ]
    patient_ids = [
        i for (i,) in session.query(PatientDB.id).filter(PatientDB.paper_id == paper_id)
    ]
    phenotype_ids = [
        i
        for (i,) in session.query(PhenotypeDB.id).filter(
            PhenotypeDB.paper_id == paper_id
        )
    ]
    variant_ids = [
        i for (i,) in session.query(VariantDB.id).filter(VariantDB.paper_id == paper_id)
    ]
    occurrence_ids = [
        i
        for (i,) in session.query(PatientVariantOccurrenceDB.id).filter(
            PatientVariantOccurrenceDB.paper_id == paper_id
        )
    ]
    segregation_evidence_ids = (
        [
            i
            for (i,) in session.query(SegregationEvidenceDB.id).filter(
                SegregationEvidenceDB.family_id.in_(family_ids)
            )
        ]
        if family_ids
        else []
    )

    # Edit history and the deletion log have no row of their own to cascade
    # from for paper-level entries (the papers row is never deleted, just
    # overwritten below), so both are deleted explicitly rather than relied
    # on to disappear for free.
    session.query(EditDB).filter(
        _paper_edit_filter(
            paper_id,
            family_ids=family_ids,
            patient_ids=patient_ids,
            variant_ids=variant_ids,
            occurrence_ids=occurrence_ids,
            segregation_evidence_ids=segregation_evidence_ids,
        )
    ).delete(synchronize_session=False)
    session.query(DeletionLogDB).filter(DeletionLogDB.paper_id == paper_id).delete(
        synchronize_session=False
    )

    session.query(TaskDB).filter(TaskDB.paper_id == paper_id).delete(
        synchronize_session=False
    )
    session.query(PatientVariantOccurrenceDB).filter(
        PatientVariantOccurrenceDB.paper_id == paper_id
    ).delete(synchronize_session=False)
    if family_ids:
        session.query(SegregationAnalysisComputedDB).filter(
            SegregationAnalysisComputedDB.family_id.in_(family_ids)
        ).delete(synchronize_session=False)
        session.query(SegregationEvidenceDB).filter(
            SegregationEvidenceDB.family_id.in_(family_ids)
        ).delete(synchronize_session=False)
    if phenotype_ids:
        session.query(HpoDB).filter(HpoDB.phenotype_id.in_(phenotype_ids)).delete(
            synchronize_session=False
        )
    if variant_ids:
        session.query(AnnotatedVariantDB).filter(
            AnnotatedVariantDB.variant_id.in_(variant_ids)
        ).delete(synchronize_session=False)
        session.query(HarmonizedVariantDB).filter(
            HarmonizedVariantDB.variant_id.in_(variant_ids)
        ).delete(synchronize_session=False)
    session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == paper_id).delete(
        synchronize_session=False
    )
    session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).delete(
        synchronize_session=False
    )
    session.query(PatientDB).filter(PatientDB.paper_id == paper_id).delete(
        synchronize_session=False
    )
    session.query(VariantDB).filter(VariantDB.paper_id == paper_id).delete(
        synchronize_session=False
    )
    session.query(FamilyDB).filter(FamilyDB.paper_id == paper_id).delete(
        synchronize_session=False
    )
    session.flush()


def restore_snapshot(
    paper_id: int, name: str, session: Session, editor: UserDB
) -> bool:
    """Replace the paper's domain rows with a snapshot's, preserving PKs.

    Runs in the caller's transaction; any failure rolls the whole reset back.
    Returns False without touching anything when the current state already
    matches the snapshot (same state hash the write-side dedupe uses), so a
    pointless reset neither churns rows nor re-stamps attribution.
    """
    path = snapshot_path(paper_id, name)
    if not path.exists():
        raise SnapshotNotFoundError(f'Snapshot {name} not found for paper {paper_id}')
    data = json.loads(path.read_text())
    if data.get('meta', {}).get('version') != SNAPSHOT_FILE_VERSION:
        raise SnapshotIncompatibleError(f'Unsupported snapshot file version in {name}')
    tables: dict = data['tables']

    paper_db = session.get(PaperDB, paper_id)
    if paper_db is None:
        raise SnapshotNotFoundError(f'Paper {paper_id} not found')

    if current_state_hash(paper_id, paper_db, session) == data.get('meta', {}).get(
        'state_hash'
    ):
        return False

    _delete_paper_domain_rows(session, paper_id)

    pair_links: dict[int, int] = {}
    for key, model in _INSERT_ORDER:
        table = _model_table(model)
        rows = [_coerce_row(table, r) for r in tables.get(key, [])]
        if key == 'patient_variant_occurrences':
            pair_links = {
                r['id']: r['paired_variant_link_id']
                for r in rows
                if r.get('paired_variant_link_id') is not None
            }
            rows = [{**r, 'paired_variant_link_id': None} for r in rows]
        if rows:
            session.execute(insert(table), rows)
    pvo_table = _model_table(PatientVariantOccurrenceDB)
    for pvo_id, link_id in pair_links.items():
        session.execute(
            update(pvo_table)
            .where(pvo_table.c.id == pvo_id)
            .values(paired_variant_link_id=link_id)
        )
    session.flush()

    paper_row = tables.get('paper', {})
    for column in _model_table(PaperDB).columns:
        if column.name in _PAPER_RESTORE_COLUMNS and column.name in paper_row:
            setattr(
                paper_db, column.name, _coerce_value(column, paper_row[column.name])
            )
    # Edit history and the deletion log for every entity above (including
    # paper-level edits) were deleted in _delete_paper_domain_rows and just
    # came back in with the rest of _INSERT_ORDER, so both now match this
    # snapshot's point in time exactly, same as every other table here --
    # nothing left to do.

    paper_db.updated_by_user_id = editor.id
    paper_db.updated_at = datetime.now(timezone.utc)
    session.flush()
    return True
