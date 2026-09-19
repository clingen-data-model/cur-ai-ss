"""backfill_edits_table_from_evidence_json

Every HumanEvidenceBlock field used to bake its own edited_by_user_id/
edited_by_name/edited_at directly into that field's *_evidence JSON column
(one copy per field, overwritten on every edit -- so only the single latest
editor per field was ever recoverable). ab0eafbeac4f added the edits table as
the new home for this, and the app's write/read paths (record_edit,
_attach_edit_history) already moved over -- but nothing had yet ported the
attribution that was already sitting in existing rows' JSON.

This is a pure data migration: no schema change, no batch_alter_table, so
none of the PRAGMA foreign_keys / CASCADE hazards documented in CLAUDE.md
apply here (see 4a424fffb965 and 3b2d941d02a2 for why those matter when they
do). For every *_evidence column on every entity table that carries
HumanEvidenceBlock data, where the JSON has a non-null edited_by_user_id:
insert one edits row carrying that attribution, then strip edited_by_user_id/
edited_by_name/edited_at out of the JSON (whether or not they were null --
those keys don't belong in the JSON at all going forward). Row-by-row in
Python, not SQLite JSON1 functions, since JSON1 isn't guaranteed compiled in
and this only runs once.

If edited_by_user_id references a user that no longer exists, the edits row
is still written with user_id left NULL (matching the column's ON DELETE SET
NULL semantics) -- editor_name is an immutable snapshot precisely so history
stays readable after a user is deleted.

Revision ID: 24aa340de723
Revises: ab0eafbeac4f
Create Date: 2026-09-18 19:15:38.562311

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '24aa340de723'
down_revision: Union[str, None] = 'ab0eafbeac4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table -> (edits FK column, [*_evidence columns carrying HumanEvidenceBlock data])
_TABLES: dict[str, tuple[str, list[str]]] = {
    'papers': (
        'paper_id',
        ['disease_name_evidence', 'disease_inheritance_mode_evidence'],
    ),
    'patients': (
        'patient_id',
        [
            'identifier_evidence',
            'proband_status_evidence',
            'sex_evidence',
            'age_diagnosis_evidence',
            'age_report_evidence',
            'age_death_evidence',
            'country_of_origin_evidence',
            'race_evidence',
            'ethnicity_evidence',
            'affected_status_evidence',
            'is_obligate_carrier_evidence',
            'relationship_to_proband_evidence',
            'twin_type_evidence',
            'family_assignment_evidence',
        ],
    ),
    'variants': (
        'variant_id',
        [
            'variant_type_evidence',
            'functional_evidence_evidence',
            'main_focus_evidence',
        ],
    ),
    'families': ('family_id', ['identifier_evidence', 'consanguinity_evidence']),
    'patient_variant_occurrences': (
        'occurrence_id',
        ['zygosity_evidence', 'inheritance_evidence', 'de_novo_evidence'],
    ),
    'segregation_evidence': (
        'segregation_evidence_id',
        ['extracted_lod_score_evidence', 'has_unexplainable_non_segregations_evidence'],
    ),
}


def upgrade() -> None:
    connection = op.get_bind()
    known_user_ids = {
        row[0] for row in connection.execute(sa.text('SELECT id FROM users'))
    }

    for table, (fk_column, columns) in _TABLES.items():
        for column in columns:
            field_name = column[: -len('_evidence')]
            rows = connection.execute(
                sa.text(f'SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL')
            ).fetchall()
            for row_id, raw_json in rows:
                if not raw_json:
                    continue
                data = json.loads(raw_json)
                user_id = data.pop('edited_by_user_id', None)
                editor_name = data.pop('edited_by_name', None)
                edited_at = data.pop('edited_at', None)
                had_attribution = user_id is not None

                if had_attribution:
                    connection.execute(
                        sa.text(
                            f'INSERT INTO edits '
                            f'({fk_column}, field_name, user_id, editor_name, edited_at) '
                            f'VALUES (:entity_id, :field_name, :user_id, :editor_name, '
                            f':edited_at)'
                        ),
                        {
                            'entity_id': row_id,
                            'field_name': field_name,
                            'user_id': user_id if user_id in known_user_ids else None,
                            'editor_name': editor_name or 'Unknown',
                            'edited_at': edited_at,
                        },
                    )

                connection.execute(
                    sa.text(f'UPDATE {table} SET {column} = :data WHERE id = :id'),
                    {'data': json.dumps(data), 'id': row_id},
                )


def downgrade() -> None:
    """Best-effort: writes each field's latest edits-table attribution back
    into its JSON. Does not delete the edits rows themselves (indistinguishable
    at this point from ones created after this migration ran) and cannot
    recover per-field history beyond the single latest edit, since that's all
    the old JSON scheme ever held either.

    Not perfectly round-trippable: a downgrade followed by a re-upgrade will
    re-discover the JSON it just restored and insert a second, duplicate edits
    row for each field (harmless -- no data is lost or corrupted, just
    redundant history -- but worth knowing before doing this on a real DB)."""
    connection = op.get_bind()

    for table, (fk_column, columns) in _TABLES.items():
        for column in columns:
            field_name = column[: -len('_evidence')]
            latest_by_entity = connection.execute(
                sa.text(
                    f'SELECT {fk_column}, user_id, editor_name, MAX(edited_at) '
                    f'FROM edits WHERE {fk_column} IS NOT NULL AND field_name = :field '
                    f'GROUP BY {fk_column}'
                ),
                {'field': field_name},
            ).fetchall()
            for entity_id, user_id, editor_name, edited_at in latest_by_entity:
                raw_json = connection.execute(
                    sa.text(f'SELECT {column} FROM {table} WHERE id = :id'),
                    {'id': entity_id},
                ).scalar()
                if not raw_json:
                    continue
                data = json.loads(raw_json)
                data['edited_by_user_id'] = user_id
                data['edited_by_name'] = editor_name
                data['edited_at'] = edited_at
                connection.execute(
                    sa.text(f'UPDATE {table} SET {column} = :data WHERE id = :id'),
                    {'data': json.dumps(data), 'id': entity_id},
                )
