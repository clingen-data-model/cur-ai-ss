#!/usr/bin/env python3
"""Remove inline HTML from stored evidence text (one-off cleanup).

A table rebuilt from its image comes back as rich markdown -- footnote markers
as ``<sup>g</sup>``, in-cell line breaks as ``<br>``, because plain markdown can
express neither. Quotes are copied from that text verbatim, as the extraction
contract requires, so the tags rode into the evidence and out to curators, who
read them literally: Streamlit escapes HTML rather than rendering it.

Blocks built from now on are cleaned as they are constructed. This does the same
for what is already stored, walking every JSON evidence and reasoning column in
the schema.

Two things it is careful about:

  - A bare "<" is not markup. "<2" is a real LDL receptor activity in these
    papers and "<1 year" a real age, so only complete tags are removed.
  - ``variants.functional_evidence`` matches the column-name pattern and is a
    BOOLEAN, not JSON. Columns are selected by declared type, not by name.

Idempotent: cleaning text that carries no markup leaves it unchanged, so a
second run reports nothing to do.

Self-contained on purpose. It has to run against a deployment that predates the
model-layer change it accompanies, so it carries its own copy of the cleaning
rules rather than importing them; a test asserts the two agree.

Usage:
    uv run python -m lib.bin.strip_evidence_markup            # report only
    uv run python -m lib.bin.strip_evidence_markup --apply    # write
"""

import json
import re
import sys
from typing import Any

from sqlalchemy import text

from lib.api.db import session_scope

_BR = re.compile(r'<br\s*/?>', re.IGNORECASE)
_FOOTNOTE = re.compile(r'<(sup|sub)>([A-Za-z]{1,2})</\1>', re.IGNORECASE)
_SUP = re.compile(r'<sup>([^<]+)</sup>', re.IGNORECASE)
_SUB = re.compile(r'<sub>([^<]+)</sub>', re.IGNORECASE)
# Only real tag names, never a catch-all. "<[^>]+>" looks equivalent and is
# not: these papers use "<" as data ("<2" of normal activity) and ">" as data
# (c.361G>C), so a greedy pattern matches from one to the other and eats what
# lies between -- "LDL activity <2 and c.361G>C" came out as "LDL activity C".
_TAG = re.compile(
    r'</?(?:br|sup|sub|b|i|em|strong|u|s|span|small|code|a|p|div|'
    r'table|thead|tbody|tr|td|th|ul|ol|li)(?:\s[^<>]*)?/?>',
    re.IGNORECASE,
)


def strip_markup(text_value: str) -> str:
    """A copy of lib.models.evidence_block.strip_markup, kept here so this runs
    on a box that does not have it yet. test_evidence_markup pins them equal."""
    if '<' not in text_value:
        return text_value
    text_value = _BR.sub(' ', text_value)
    text_value = _FOOTNOTE.sub('', text_value)
    text_value = _SUP.sub(r'^\1', text_value)
    text_value = _SUB.sub(r'_\1', text_value)
    text_value = _TAG.sub('', text_value)
    return re.sub(r'[ \t]+', ' ', text_value).strip()


# The keys a curator actually reads. Everything else in a block is structural.
TEXT_KEYS = ('quote', 'reasoning', 'human_edit_note')

_COLUMNS = text("""
    SELECT m.name AS tbl, p.name AS col
      FROM sqlite_master m, pragma_table_info(m.name) p
     WHERE m.type = 'table'
       AND p.type = 'JSON'
       AND (p.name LIKE '%_evidence' OR p.name LIKE '%_reasoning')
     ORDER BY m.name, p.name
""")


def _clean(node: Any) -> int:
    """Clean the text a curator sees, in place. Returns fields changed."""
    changed = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TEXT_KEYS and isinstance(value, str):
                cleaned = strip_markup(value)
                if cleaned != value:
                    node[key] = cleaned
                    changed += 1
            else:
                changed += _clean(value)
    elif isinstance(node, list):
        for item in node:
            changed += _clean(item)
    return changed


def strip_stored_markup(apply: bool = False) -> tuple[int, int]:
    """Returns (fields cleaned, rows affected)."""
    fields = rows = 0
    with session_scope() as session:
        columns = session.execute(_COLUMNS).fetchall()
        for table, column in columns:
            # Only rows that could hold a tag at all; "<" is cheap to test and
            # keeps this from rewriting the whole corpus.
            candidates = session.execute(
                text(
                    f'SELECT rowid, "{column}" FROM "{table}" '  # noqa: S608
                    f'WHERE "{column}" LIKE \'%<%\''
                )
            ).fetchall()
            for rowid, raw in candidates:
                if not raw:
                    continue
                try:
                    decoded = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                changed = _clean(decoded)
                if not changed:
                    continue
                fields += changed
                rows += 1
                if apply:
                    session.execute(
                        text(
                            f'UPDATE "{table}" SET "{column}" = :value '  # noqa: S608
                            f'WHERE rowid = :rowid'
                        ),
                        {'value': json.dumps(decoded), 'rowid': rowid},
                    )
        verb = 'cleaned' if apply else 'would clean'
        print(
            f'{verb} {fields} fields across {rows} rows '
            f'in {len(columns)} evidence columns'
        )
        if not apply and rows:
            print('re-run with --apply to write')
        if not apply:
            session.rollback()
    return fields, rows


if __name__ == '__main__':
    extra = set(sys.argv[1:]) - {'--apply'}
    if extra:
        print(f'Usage: {sys.argv[0]} [--apply]', file=sys.stderr)
        sys.exit(1)
    strip_stored_markup(apply='--apply' in sys.argv[1:])
