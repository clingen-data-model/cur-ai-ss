"""Versioned on-disk snapshots of a paper's extracted database state.

A snapshot is one JSON file under ``<pdf_dir>/snapshots/`` holding a faithful
column dump of every paper-scoped table, written when the extraction pipeline
completes. Restoring wipes the paper's domain rows and re-inserts them with
their original primary keys, so ``tasks`` rows (whose scope FKs point at those
ids) survive a reset.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from sqlalchemy import Column, DateTime, Table, insert, text, update
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from lib.misc.pdf.paths import snapshots_dir
from lib.models import (
    AgentRunDB,
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
    SnapshotMeta,
    TaskDB,
    UserDB,
    VariantDB,
)
from lib.models.base import row_to_dict

logger = logging.getLogger(__name__)

SNAPSHOT_FILE_VERSION = 1

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
]

# tasks scope column -> snapshot table its values must exist in after restore
_TASK_SCOPE_COLUMNS: dict[str, str] = {
    'family_id': 'families',
    'patient_id': 'patients',
    'variant_id': 'variants',
    'phenotype_id': 'phenotypes',
    'patient_variant_occurrence_id': 'patient_variant_occurrences',
}

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

# Attribution columns churn on every task completion without representing
# extraction output, so they don't participate in change detection.
_HASH_EXCLUDED_KEYS = {'updated_at', 'updated_by_user_id'}


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


def _current_alembic_revision(session: Session) -> str | None:
    bind = session.get_bind()
    if not sa_inspect(bind).has_table('alembic_version'):
        return None
    return session.execute(text('SELECT version_num FROM alembic_version')).scalar()


def list_snapshots(paper_id: int) -> list[SnapshotMeta]:
    """Read the meta block of every snapshot for a paper, newest first."""
    directory = snapshots_dir(paper_id)
    if not directory.exists():
        return []
    metas: list[SnapshotMeta] = []
    for path in directory.glob('extraction_*.json'):
        if not _SNAPSHOT_NAME_RE.match(path.name):
            continue
        try:
            meta = json.loads(path.read_text())['meta']
            metas.append(SnapshotMeta(name=path.name, **meta))
        except (OSError, ValueError, KeyError):
            logger.warning('Skipping unreadable snapshot %s', path)
    metas.sort(key=lambda m: m.created_at, reverse=True)
    return metas


def write_snapshot(paper_id: int, session: Session) -> Path | None:
    """Write a new snapshot unless the latest one already matches current state."""
    paper_db = session.get(PaperDB, paper_id)
    if paper_db is None:
        return None

    encoded = _encode_tables(dump_paper_state(paper_id, paper_db, session))
    state_hash = _state_hash(encoded)
    existing = list_snapshots(paper_id)
    if existing and existing[0].state_hash == state_hash:
        return None

    agent_run = (
        session.query(AgentRunDB)
        .join(TaskDB, TaskDB.agent_run_id == AgentRunDB.id)
        .filter(TaskDB.paper_id == paper_id)
        .order_by(AgentRunDB.updated_at.desc(), AgentRunDB.id.desc())
        .first()
    )
    now = datetime.now(timezone.utc)
    meta = {
        'version': SNAPSHOT_FILE_VERSION,
        'created_at': now.isoformat(),
        'paper_id': paper_id,
        'alembic_revision': _current_alembic_revision(session),
        'agent_run_id': agent_run.id if agent_run else None,
        'model': agent_run.model if agent_run else None,
        'git_hash': agent_run.git_hash if agent_run else None,
        'state_hash': state_hash,
    }

    name = f'extraction_{now:%Y%m%dT%H%M%S%f}Z.json'
    path = snapshot_path(paper_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix('.tmp')
    tmp_path.write_text(json.dumps({'meta': meta, 'tables': encoded}))
    os.replace(tmp_path, path)
    logger.info('Wrote extraction snapshot %s for paper %s', name, paper_id)
    return path


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
    """Bulk-delete the paper's domain rows child-first (task FKs must already
    be detached so nothing cascades into ``tasks``)."""
    family_ids = [
        i for (i,) in session.query(FamilyDB.id).filter(FamilyDB.paper_id == paper_id)
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
) -> None:
    """Replace the paper's domain rows with a snapshot's, preserving PKs.

    Runs in the caller's transaction; any failure rolls the whole reset back.
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

    # Detach task scope FKs so deleting domain rows cannot cascade into tasks.
    tasks = session.query(TaskDB).filter(TaskDB.paper_id == paper_id).all()
    saved_scopes: dict[int, dict[str, int | None]] = {}
    for task in tasks:
        scope = {col: getattr(task, col) for col in _TASK_SCOPE_COLUMNS}
        if any(v is not None for v in scope.values()):
            saved_scopes[task.id] = scope
            for col in _TASK_SCOPE_COLUMNS:
                setattr(task, col, None)
    session.flush()

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

    # Re-attach task scopes that resolve in the restored state; drop scoped
    # tasks pointing at post-snapshot entities (what CASCADE would have done).
    restored_ids = {
        col: {r['id'] for r in tables.get(key, [])}
        for col, key in _TASK_SCOPE_COLUMNS.items()
    }
    for task in tasks:
        saved = saved_scopes.get(task.id)
        if saved is None:
            continue
        if all(v is None or v in restored_ids[col] for col, v in saved.items()):
            for col, v in saved.items():
                setattr(task, col, v)
        else:
            session.delete(task)
    session.flush()

    paper_row = tables.get('paper', {})
    for column in _model_table(PaperDB).columns:
        if column.name in _PAPER_RESTORE_COLUMNS and column.name in paper_row:
            setattr(
                paper_db, column.name, _coerce_value(column, paper_row[column.name])
            )
    paper_db.updated_by_user_id = editor.id
    paper_db.updated_at = datetime.now(timezone.utc)
    session.flush()
