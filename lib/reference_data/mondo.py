"""SQLite-backed MONDO ontology retrieval and disease-name matching."""

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from agents import RunConfig, Runner
from pydantic import BaseModel
from rapidfuzz import fuzz

from lib.core.environment import env

MONDO_ONTOLOGY_ENDPOINT = 'https://purl.obolibrary.org/obo/mondo.json'
MONDO_IRI_PREFIX = 'http://purl.obolibrary.org/obo/MONDO_'
MONDO_ID_RE = re.compile(
    r'^(?:https?://purl\.obolibrary\.org/obo/)?MONDO[:_](\d+)$',
    re.IGNORECASE,
)
MONDO_ID_IN_TEXT_RE = re.compile(
    r'(?:https?://purl\.obolibrary\.org/obo/)?MONDO[:_](\d+)\b',
    re.IGNORECASE,
)
OBO_IRI_RE = re.compile(r'https?://purl\.obolibrary\.org/obo/([A-Za-z]+)_(.+)$')
ORPHANET_IRI_RE = re.compile(r'https?://www\.orpha\.net/ORDO/Orphanet_(\d+)$')
OMIM_IRI_RE = re.compile(r'https?://omim\.org/entry/(\d+)$')
IDENTIFIERS_IRI_RE = re.compile(r'https?://identifiers\.org/([^/]+)/(.+)$')
ICD_IRI_RE = re.compile(r'https?://id\.who\.int/icd/entity/(.+)$')
CURIE_IN_TEXT_RE = re.compile(r'\b[A-Za-z][A-Za-z0-9_.-]*:[A-Za-z0-9_.-]+\b')
URL_IN_TEXT_RE = re.compile(r'https?://[^\s<>)\]},"\']+')

SKOS_EXACT_MATCH = 'http://www.w3.org/2004/02/skos/core#exactMatch'
DEPRECATED_REPLACEMENT_PREDICATES = {
    'http://purl.obolibrary.org/obo/IAO_0100001',
    'http://www.geneontology.org/formats/oboInOwl#consider',
}
ABBREVIATION_TYPE = 'http://purl.obolibrary.org/obo/mondo#ABBREVIATION'
EXCLUDED_SYNONYM_TYPE_TOKENS = (
    'AMBIGUOUS',
    'DEPRECATED',
    'DUBIOUS',
    'MISSPELLING',
)
STRICT_DASHES_RE = re.compile(r'[\u2010-\u2015\u2212]')
FUZZY_PUNCTUATION_RE = re.compile(r'[\W_]+')
FUZZY_SCORE_CUTOFF = 85.0

_mondo_index: 'MondoIndex | None' = None


class MondoTerm(BaseModel):
    mondo_id: str
    term: str
    match_type: str | None = None
    matched_text: str | None = None
    score: float | None = None
    match_context: dict[str, Any] | None = None


class MondoDiseaseContext(BaseModel):
    paper_title: str | None = None
    paper_abstract: str | None = None
    paper_disease_name: str | None = None
    occurrence_disease_text: str | None = None
    gene_symbol: str | None = None
    inheritance_mode: str | None = None


class MondoCandidate(BaseModel):
    mondo_id: str
    label: str
    matched_alias_text: str
    alias_type: str
    retrieval_source: str
    source_priority: int
    definition: str | None = None
    fts_rank: float | None = None
    rapidfuzz_score: float | None = None


@dataclass(frozen=True)
class MondoIndex:
    sqlite_path: Path
    ontology_path: Path | None = None
    has_trigram_fts: bool = True


@dataclass(frozen=True)
class MatchEntry:
    mondo_id: str
    label: str
    matched_text: str
    match_type: str
    source_priority: int
    definition: str | None = None

    def context(self, score: float | None = None) -> dict[str, Any]:
        context: dict[str, Any] = {
            'mondo_id': self.mondo_id,
            'term': self.label,
            'matched_text': self.matched_text,
            'match_type': self.match_type,
        }
        if score is not None:
            context['score'] = float(score)
        return context


@dataclass(frozen=True)
class DeterministicLookup:
    selected: MondoTerm | None
    strict_ambiguities: list[dict[str, Any]]


def ontology_path() -> Path:
    """Return the local path for the MONDO ontology JSON file."""
    return env.reference_data_dir / 'mondo.json'


def sqlite_path() -> Path:
    """Return the local path for the MONDO SQLite index."""
    return env.reference_data_dir / 'mondo.sqlite'


def ontology_url() -> str:
    """Return the configured MONDO ontology download URL."""
    return getattr(env, 'MONDO_ONTOLOGY_URL', MONDO_ONTOLOGY_ENDPOINT)


def download_ontology() -> Path:
    """Download the MONDO ontology JSON file to the local reference-data path."""
    path = ontology_path()
    tmp_path = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(ontology_url(), stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp_path.replace(path)
    return path


def ensure_ontology() -> Path:
    """Return the local ontology path, downloading the file if necessary."""
    path = ontology_path()
    if not path.exists():
        return download_ontology()
    return path


def ensure_mondo_sqlite() -> Path:
    """Return the SQLite index path, building it from MONDO JSON if missing."""
    path = sqlite_path()
    if not path.exists():
        build_mondo_index(ensure_ontology(), path)
    return path


def get_mondo_index() -> MondoIndex:
    """Return the process-local MONDO SQLite index descriptor."""
    global _mondo_index
    if _mondo_index is None:
        path = sqlite_path()
        if not path.exists():
            _mondo_index = build_mondo_index(ensure_ontology(), path)
        else:
            _mondo_index = MondoIndex(
                sqlite_path=path,
                has_trigram_fts=sqlite_has_trigram_fts(path),
            )
    return _mondo_index


def build_mondo_index(path: Path, target_sqlite_path: Path | None = None) -> MondoIndex:
    """Build a SQLite MONDO index from OWLGraph JSON.

    Args:
        path: Path to the MONDO OWLGraph JSON ontology file.
        target_sqlite_path: Optional output path. Defaults to ``path`` with a
            ``.sqlite`` suffix.

    Returns:
        A MondoIndex descriptor for the created SQLite index.
    """
    db_path = target_sqlite_path or path.with_suffix('.sqlite')
    has_trigram_fts = build_mondo_sqlite(path, db_path)
    return MondoIndex(
        sqlite_path=db_path,
        ontology_path=path,
        has_trigram_fts=has_trigram_fts,
    )


def build_mondo_sqlite(path: Path, db_path: Path) -> bool:
    """Create the SQLite schema and populate it from MONDO JSON."""
    with open(path) as f:
        data = json.load(f)
    graphs = data.get('graphs') or []
    if not graphs:
        raise RuntimeError(f'MONDO ontology file has no graphs: {path}')

    graph = graphs[0]
    nodes = graph.get('nodes') or []
    edges = graph.get('edges') or []
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(f'{db_path.suffix}.tmp')
    if tmp_path.exists():
        tmp_path.unlink()

    non_deprecated_nodes: dict[str, dict[str, Any]] = {}
    deprecated_nodes: list[dict[str, Any]] = []
    for node in nodes:
        iri = node.get('id')
        label = node.get('lbl')
        if not isinstance(iri, str) or not iri.startswith(MONDO_IRI_PREFIX):
            continue
        if node.get('type') != 'CLASS' or not isinstance(label, str):
            continue
        mondo_id = iri_to_mondo_id(iri)
        if mondo_id is None:
            continue
        if is_deprecated_node(node):
            deprecated_nodes.append(node)
        else:
            non_deprecated_nodes[mondo_id] = node

    conn = sqlite3.connect(tmp_path)
    conn.row_factory = sqlite3.Row
    has_trigram_fts = True
    try:
        create_schema(conn)
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE mondo_alias_trigram_fts
                USING fts5(
                    normalized_alias,
                    alias_id UNINDEXED,
                    tokenize='trigram'
                )
                """
            )
        except sqlite3.OperationalError:
            has_trigram_fts = False

        for mondo_id, node in sorted(non_deprecated_nodes.items()):
            insert_term(conn, mondo_id, node, deprecated=False)
            insert_alias(
                conn,
                mondo_id,
                node['lbl'],
                'primary_label',
                source_priority=0,
                include_in_fts=True,
                has_trigram_fts=has_trigram_fts,
            )
            meta = node.get('meta') or {}
            for synonym in meta.get('synonyms') or []:
                insert_synonym_alias(conn, mondo_id, synonym, has_trigram_fts)
            for xref in meta.get('xrefs') or []:
                val = xref.get('val') if isinstance(xref, dict) else None
                if isinstance(val, str):
                    insert_identifier(conn, mondo_id, val, 'xref')
            for basic_property in meta.get('basicPropertyValues') or []:
                if not isinstance(basic_property, dict):
                    continue
                if basic_property.get('pred') == SKOS_EXACT_MATCH and isinstance(
                    basic_property.get('val'), str
                ):
                    insert_identifier(
                        conn,
                        mondo_id,
                        basic_property['val'],
                        'exact_mapping_id',
                    )

        for node in deprecated_nodes:
            insert_deprecated_replacement_aliases(
                conn,
                node,
                set(non_deprecated_nodes),
                has_trigram_fts,
            )

        for edge in edges:
            insert_edge(conn, edge)

        create_indexes(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    tmp_path.replace(db_path)
    return has_trigram_fts


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the production MONDO SQLite tables."""
    conn.executescript(
        """
        CREATE TABLE mondo_terms (
            mondo_id TEXT PRIMARY KEY,
            iri TEXT NOT NULL,
            label TEXT NOT NULL,
            definition TEXT,
            deprecated INTEGER NOT NULL DEFAULT 0,
            replacement_mondo_id TEXT
        );

        CREATE TABLE mondo_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mondo_id TEXT NOT NULL,
            alias_text TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            alias_type TEXT NOT NULL,
            source_priority INTEGER NOT NULL,
            FOREIGN KEY (mondo_id) REFERENCES mondo_terms(mondo_id)
        );

        CREATE TABLE mondo_xrefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mondo_id TEXT NOT NULL,
            identifier TEXT NOT NULL,
            normalized_identifier TEXT NOT NULL,
            xref_type TEXT NOT NULL,
            FOREIGN KEY (mondo_id) REFERENCES mondo_terms(mondo_id)
        );

        CREATE TABLE mondo_edges (
            subject_mondo_id TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_mondo_id TEXT NOT NULL
        );

        CREATE TABLE mondo_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


def create_indexes(conn: sqlite3.Connection) -> None:
    """Create B-tree indexes used by deterministic lookup tiers."""
    conn.executescript(
        """
        CREATE INDEX idx_mondo_aliases_lookup
            ON mondo_aliases(normalized_alias, alias_type);
        CREATE INDEX idx_mondo_aliases_mondo_id
            ON mondo_aliases(mondo_id);
        CREATE INDEX idx_mondo_xrefs_lookup
            ON mondo_xrefs(normalized_identifier);
        CREATE INDEX idx_mondo_xrefs_mondo_id
            ON mondo_xrefs(mondo_id);
        CREATE INDEX idx_mondo_edges_subject
            ON mondo_edges(subject_mondo_id);
        CREATE INDEX idx_mondo_edges_object
            ON mondo_edges(object_mondo_id);
        """
    )


def insert_term(
    conn: sqlite3.Connection,
    mondo_id: str,
    node: dict[str, Any],
    deprecated: bool,
    replacement_mondo_id: str | None = None,
) -> None:
    """Insert one MONDO term row."""
    conn.execute(
        """
        INSERT OR REPLACE INTO mondo_terms (
            mondo_id, iri, label, definition, deprecated, replacement_mondo_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            mondo_id,
            node['id'],
            node['lbl'],
            extract_definition(node),
            int(deprecated),
            replacement_mondo_id,
        ),
    )


def insert_alias(
    conn: sqlite3.Connection,
    mondo_id: str,
    alias_text: str,
    alias_type: str,
    source_priority: int,
    include_in_fts: bool,
    has_trigram_fts: bool,
) -> None:
    """Insert one alias and optionally mirror it into the trigram FTS table."""
    normalized_alias = normalize_strict(alias_text)
    if not normalized_alias:
        return
    cursor = conn.execute(
        """
        INSERT INTO mondo_aliases (
            mondo_id, alias_text, normalized_alias, alias_type, source_priority
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (mondo_id, alias_text, normalized_alias, alias_type, source_priority),
    )
    if include_in_fts and has_trigram_fts:
        conn.execute(
            """
            INSERT INTO mondo_alias_trigram_fts (
                rowid, normalized_alias, alias_id
            )
            VALUES (?, ?, ?)
            """,
            (cursor.lastrowid, normalize_fuzzy(alias_text), cursor.lastrowid),
        )


def insert_synonym_alias(
    conn: sqlite3.Connection,
    mondo_id: str,
    synonym: dict[str, Any],
    has_trigram_fts: bool,
) -> None:
    """Insert a MONDO synonym into the appropriate alias tier."""
    val = synonym.get('val')
    pred = synonym.get('pred')
    synonym_type = synonym.get('synonymType')
    if not isinstance(val, str) or not isinstance(pred, str):
        return
    if is_excluded_synonym_type(synonym_type):
        return

    if synonym_type == ABBREVIATION_TYPE:
        insert_alias(
            conn,
            mondo_id,
            val,
            'abbreviation',
            source_priority=3,
            include_in_fts=False,
            has_trigram_fts=has_trigram_fts,
        )
        return

    if pred == 'hasExactSynonym':
        insert_alias(conn, mondo_id, val, 'exact_synonym', 1, True, has_trigram_fts)
    elif pred == 'hasRelatedSynonym':
        insert_alias(conn, mondo_id, val, 'related_synonym', 2, True, has_trigram_fts)
    elif pred in {'hasBroadSynonym', 'hasNarrowSynonym'}:
        insert_alias(conn, mondo_id, val, pred, 4, False, has_trigram_fts)


def insert_identifier(
    conn: sqlite3.Connection,
    mondo_id: str,
    identifier: str,
    xref_type: str,
) -> None:
    """Insert normalized lookup keys for one external identifier."""
    for key in normalize_identifier_keys(identifier):
        conn.execute(
            """
            INSERT INTO mondo_xrefs (
                mondo_id, identifier, normalized_identifier, xref_type
            )
            VALUES (?, ?, ?, ?)
            """,
            (mondo_id, identifier, key, xref_type),
        )


def insert_deprecated_replacement_aliases(
    conn: sqlite3.Connection,
    node: dict[str, Any],
    valid_mondo_ids: set[str],
    has_trigram_fts: bool,
) -> None:
    """Index deprecated node text when it has exactly one valid replacement."""
    replacement_ids = []
    meta = node.get('meta') or {}
    for basic_property in meta.get('basicPropertyValues') or []:
        if not isinstance(basic_property, dict):
            continue
        if basic_property.get('pred') not in DEPRECATED_REPLACEMENT_PREDICATES:
            continue
        val = basic_property.get('val')
        if not isinstance(val, str):
            continue
        mondo_id = iri_to_mondo_id(val) or normalize_mondo_id(val)
        if mondo_id and mondo_id in valid_mondo_ids:
            replacement_ids.append(mondo_id)

    distinct_replacements = sorted(set(replacement_ids))
    deprecated_mondo_id = iri_to_mondo_id(node.get('id', ''))
    if deprecated_mondo_id:
        insert_term(
            conn,
            deprecated_mondo_id,
            node,
            deprecated=True,
            replacement_mondo_id=distinct_replacements[0]
            if len(distinct_replacements) == 1
            else None,
        )
    if len(distinct_replacements) != 1:
        return

    deprecated_texts = set()
    if isinstance(node.get('lbl'), str):
        deprecated_texts.add(node['lbl'])
    if deprecated_mondo_id:
        deprecated_texts.add(deprecated_mondo_id)
        deprecated_texts.add(deprecated_mondo_id.replace(':', '_'))
    for synonym in meta.get('synonyms') or []:
        val = synonym.get('val') if isinstance(synonym, dict) else None
        if isinstance(val, str):
            deprecated_texts.add(val)

    for text in deprecated_texts:
        insert_alias(
            conn,
            distinct_replacements[0],
            text,
            'deprecated_replacement',
            source_priority=5,
            include_in_fts=False,
            has_trigram_fts=has_trigram_fts,
        )


def insert_edge(conn: sqlite3.Connection, edge: dict[str, Any]) -> None:
    """Insert one MONDO-to-MONDO graph edge when both endpoints are MONDO terms."""
    subject = iri_to_mondo_id(edge.get('sub', ''))
    obj = iri_to_mondo_id(edge.get('obj', ''))
    pred = edge.get('pred')
    if not subject or not obj or not isinstance(pred, str):
        return
    conn.execute(
        """
        INSERT INTO mondo_edges (subject_mondo_id, predicate, object_mondo_id)
        VALUES (?, ?, ?)
        """,
        (subject, pred, obj),
    )


def find_mondo_term_for_disease(disease_name: str) -> MondoTerm | None:
    """Return the selected MONDO term for a disease name without agent calls."""
    query = disease_name.strip()
    if not query:
        return None

    index = get_mondo_index()
    deterministic = deterministic_sql_lookup(index, query)
    if deterministic.selected is not None:
        return deterministic.selected
    if deterministic.strict_ambiguities:
        return None

    candidates = retrieve_mondo_candidates(index, query, limit=10)
    if not candidates:
        return None

    selected = candidates[0]
    score = selected.rapidfuzz_score or 0.0
    if score < FUZZY_SCORE_CUTOFF:
        return None

    context = build_match_context(
        query=query,
        selected=MondoTerm(
            mondo_id=selected.mondo_id,
            term=selected.label,
            match_type='fuzzy',
            matched_text=selected.matched_alias_text,
            score=float(score),
        ),
        candidates=candidates,
        strict_ambiguities=deterministic.strict_ambiguities,
        agent_used=False,
    )
    context.update(
        {
            'scorer': 'rapidfuzz.fuzz.token_sort_ratio',
            'nearest_candidates': [
                candidate_to_legacy_context(candidate) for candidate in candidates
            ],
            'selected_score': float(score),
            'selected_matched_text': selected.matched_alias_text,
            'selected_match_type': selected.alias_type,
        }
    )
    return MondoTerm(
        mondo_id=selected.mondo_id,
        term=selected.label,
        match_type='fuzzy',
        matched_text=selected.matched_alias_text,
        score=float(score),
        match_context=context,
    )


async def find_mondo_term_for_disease_with_agent(
    disease_name: str,
    context: MondoDiseaseContext | None = None,
) -> MondoTerm | None:
    """Return a MONDO term, using the agent for ambiguous or uncertain cases."""
    query = disease_name.strip()
    if not query:
        return None

    index = get_mondo_index()
    deterministic = deterministic_sql_lookup(index, query)
    if deterministic.selected is not None:
        return deterministic.selected

    candidates = retrieve_mondo_candidates(index, query, limit=20)
    message = {
        'disease_name': query,
        'context': context.model_dump(exclude_none=True) if context else {},
        'initial_candidates': [c.model_dump() for c in candidates],
        'strict_ambiguities': deterministic.strict_ambiguities,
    }

    from lib.agents.mondo_linking_agent import MONDO_LINKING_AGENT_INSTRUCTIONS
    from lib.agents.mondo_linking_agent import agent as mondo_linking_agent

    result = await Runner.run(
        mondo_linking_agent,
        (
            f'MONDO linking JSON:\n{json.dumps(message, indent=2)}\n\n'
            f'{MONDO_LINKING_AGENT_INSTRUCTIONS}'
        ),
        max_turns=12,
        run_config=RunConfig(
            trace_metadata={
                'disease_name': query,
                'gene_symbol': context.gene_symbol if context else '',
            },
        ),
    )
    decision = result.final_output.value
    if not decision.mondo_id:
        return None

    selected_term = get_mondo_term(decision.mondo_id)
    if selected_term is None:
        return None

    selected = MondoTerm(
        mondo_id=selected_term['mondo_id'],
        term=selected_term['label'],
        match_type=decision.match_type or 'agent_selected',
        matched_text=decision.matched_text or query,
        score=decision.confidence_score,
    )
    selected.match_context = build_match_context(
        query=query,
        selected=selected,
        candidates=candidates,
        strict_ambiguities=deterministic.strict_ambiguities,
        agent_used=True,
        agent_reasoning=result.final_output.reasoning,
        candidates_considered=decision.candidates_considered,
        confidence=decision.confidence,
    )
    return selected


def deterministic_sql_lookup(index: MondoIndex, query: str) -> DeterministicLookup:
    """Run strict deterministic SQL lookup tiers."""
    strict_ambiguities: list[dict[str, Any]] = []
    direct_matches = []
    with connect_index(index) as conn:
        for mondo_id in extract_mondo_ids(query):
            row = conn.execute(
                """
                SELECT mondo_id, label, definition
                FROM mondo_terms
                WHERE mondo_id = ? AND deprecated = 0
                """,
                (mondo_id,),
            ).fetchone()
            if row:
                direct_matches.append(
                    MatchEntry(
                        mondo_id=row['mondo_id'],
                        label=row['label'],
                        matched_text=mondo_id,
                        match_type='direct_mondo_id',
                        source_priority=0,
                        definition=row['definition'],
                    )
                )
        selected, ambiguity = select_unique_entry(
            'direct_mondo_id', query, direct_matches
        )
        if selected is not None:
            return DeterministicLookup(
                term_from_entry(selected, 'direct_mondo_id', query),
                strict_ambiguities,
            )
        if ambiguity is not None:
            strict_ambiguities.append(ambiguity)

        strict_steps: list[tuple[str, str | set[str], tuple[str, ...]]] = [
            ('primary_label', normalize_strict(query), ('primary_label',)),
            ('exact_synonym', normalize_strict(query), ('exact_synonym',)),
            ('xref', extract_identifier_keys(query), ()),
            ('related_synonym', normalize_strict(query), ('related_synonym',)),
            (
                'broad_narrow_synonym',
                normalize_strict(query),
                ('hasBroadSynonym', 'hasNarrowSynonym'),
            ),
            ('abbreviation', normalize_strict(query), ('abbreviation',)),
            (
                'deprecated_replacement',
                normalize_strict(query),
                ('deprecated_replacement',),
            ),
        ]
        for match_type, lookup_key, alias_types in strict_steps:
            if match_type == 'xref':
                entries = xref_entries_for_lookup(conn, lookup_key)
            else:
                entries = alias_entries_for_lookup(conn, lookup_key, alias_types)
            selected, ambiguity = select_unique_entry(match_type, query, entries)
            if selected is not None:
                return DeterministicLookup(
                    term_from_entry(selected, selected.match_type, query),
                    strict_ambiguities,
                )
            if ambiguity is not None:
                strict_ambiguities.append(ambiguity)

    return DeterministicLookup(None, strict_ambiguities)


def retrieve_mondo_candidates(
    index: MondoIndex,
    query: str,
    strategy: str = 'combined',
    limit: int = 20,
) -> list[MondoCandidate]:
    """Retrieve and rerank MONDO candidates from SQLite-backed aliases."""
    normalized_query = normalize_fuzzy(query)
    if not normalized_query:
        return []

    with connect_index(index) as conn:
        alias_rows: list[sqlite3.Row] = []
        if strategy in {'combined', 'trigram_fts'} and index.has_trigram_fts:
            alias_rows = query_trigram_fts(
                conn, normalized_query, limit=max(200, limit * 20)
            )
        if not alias_rows and strategy in {'combined', 'rapidfuzz'}:
            alias_rows = query_all_fuzzy_aliases(conn)

    if not alias_rows:
        return []

    scored: list[MondoCandidate] = []
    for row in alias_rows:
        score = fuzz.token_sort_ratio(normalized_query, normalize_fuzzy(row['alias_text']))
        scored.append(
            MondoCandidate(
                mondo_id=row['mondo_id'],
                label=row['label'],
                definition=row['definition'],
                matched_alias_text=row['alias_text'],
                alias_type=row['alias_type'],
                source_priority=row['source_priority'],
                retrieval_source=row['retrieval_source'],
                fts_rank=row['fts_rank'],
                rapidfuzz_score=float(score),
            )
        )

    best_by_mondo_id: dict[str, MondoCandidate] = {}
    for candidate in scored:
        existing = best_by_mondo_id.get(candidate.mondo_id)
        if existing is None or candidate_sort_key(candidate, normalized_query) < (
            candidate_sort_key(existing, normalized_query)
        ):
            best_by_mondo_id[candidate.mondo_id] = candidate

    return sorted(
        best_by_mondo_id.values(),
        key=lambda candidate: candidate_sort_key(candidate, normalized_query),
    )[:limit]


def query_trigram_fts(
    conn: sqlite3.Connection,
    normalized_query: str,
    limit: int,
) -> list[sqlite3.Row]:
    """Query the trigram FTS table and return alias rows."""
    fts_query = fts5_trigram_query(normalized_query)
    if not fts_query:
        return []
    try:
        return list(
            conn.execute(
                """
                SELECT
                    a.mondo_id,
                    t.label,
                    t.definition,
                    a.alias_text,
                    a.alias_type,
                    a.source_priority,
                    'trigram_fts' AS retrieval_source,
                    bm25(mondo_alias_trigram_fts) AS fts_rank
                FROM mondo_alias_trigram_fts
                JOIN mondo_aliases a ON a.id = mondo_alias_trigram_fts.alias_id
                JOIN mondo_terms t ON t.mondo_id = a.mondo_id
                WHERE mondo_alias_trigram_fts MATCH ?
                    AND t.deprecated = 0
                ORDER BY fts_rank
                LIMIT ?
                """,
                (fts_query, limit),
            )
        )
    except sqlite3.OperationalError:
        return []


def fts5_trigram_query(normalized_query: str) -> str:
    """Return a permissive FTS5 query over quoted trigrams."""
    grams = []
    seen = set()
    for idx in range(max(len(normalized_query) - 2, 0)):
        gram = normalized_query[idx : idx + 3].strip()
        if len(gram) < 3 or gram in seen:
            continue
        seen.add(gram)
        grams.append(f'"{gram.replace("\"", "\"\"")}"')
    return ' OR '.join(grams)


def query_all_fuzzy_aliases(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all fuzzy-eligible aliases for RapidFuzz fallback reranking."""
    return list(
        conn.execute(
            """
            SELECT
                a.mondo_id,
                t.label,
                t.definition,
                a.alias_text,
                a.alias_type,
                a.source_priority,
                'rapidfuzz' AS retrieval_source,
                NULL AS fts_rank
            FROM mondo_aliases a
            JOIN mondo_terms t ON t.mondo_id = a.mondo_id
            WHERE t.deprecated = 0
                AND a.alias_type IN ('primary_label', 'exact_synonym', 'related_synonym')
            """
        )
    )


def get_mondo_term(mondo_id: str) -> dict[str, Any] | None:
    """Return MONDO term details for tools and agent validation."""
    normalized_id = normalize_mondo_id(mondo_id)
    if normalized_id is None:
        return None
    index = get_mondo_index()
    with connect_index(index) as conn:
        row = conn.execute(
            """
            SELECT mondo_id, iri, label, definition, deprecated, replacement_mondo_id
            FROM mondo_terms
            WHERE mondo_id = ?
            """,
            (normalized_id,),
        ).fetchone()
        if not row:
            return None
        aliases = [
            dict(alias)
            for alias in conn.execute(
                """
                SELECT alias_text, alias_type, source_priority
                FROM mondo_aliases
                WHERE mondo_id = ?
                ORDER BY source_priority, alias_text
                """,
                (normalized_id,),
            )
        ]
        xrefs = [
            dict(xref)
            for xref in conn.execute(
                """
                SELECT identifier, xref_type
                FROM mondo_xrefs
                WHERE mondo_id = ?
                ORDER BY xref_type, identifier
                """,
                (normalized_id,),
            )
        ]
    return {
        'mondo_id': row['mondo_id'],
        'iri': row['iri'],
        'label': row['label'],
        'definition': row['definition'],
        'deprecated': bool(row['deprecated']),
        'replacement_mondo_id': row['replacement_mondo_id'],
        'aliases': aliases,
        'xrefs': xrefs,
    }


def get_mondo_related_terms(mondo_id: str, direction: str) -> list[dict[str, Any]]:
    """Return parent or child MONDO terms connected by ontology edges."""
    normalized_id = normalize_mondo_id(mondo_id)
    if normalized_id is None:
        return []
    if direction == 'parents':
        predicate_column = 'subject_mondo_id'
        related_column = 'object_mondo_id'
    else:
        predicate_column = 'object_mondo_id'
        related_column = 'subject_mondo_id'
    index = get_mondo_index()
    with connect_index(index) as conn:
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    t.mondo_id,
                    t.label,
                    t.definition,
                    e.predicate
                FROM mondo_edges e
                JOIN mondo_terms t ON t.mondo_id = e.{related_column}
                WHERE e.{predicate_column} = ?
                    AND t.deprecated = 0
                ORDER BY t.label
                LIMIT 100
                """,
                (normalized_id,),
            )
        ]


def get_mondo_terms_by_xref(identifier: str) -> list[dict[str, Any]]:
    """Return MONDO terms matching an external identifier."""
    index = get_mondo_index()
    keys = extract_identifier_keys(identifier)
    if not keys:
        return []
    with connect_index(index) as conn:
        entries = xref_entries_for_lookup(conn, keys)
    return [
        {
            'mondo_id': entry.mondo_id,
            'label': entry.label,
            'definition': entry.definition,
            'matched_identifier': entry.matched_text,
            'xref_type': entry.match_type,
        }
        for entry in entries
    ]


def alias_entries_for_lookup(
    conn: sqlite3.Connection,
    lookup_key: str | set[str],
    alias_types: tuple[str, ...],
) -> list[MatchEntry]:
    """Return alias entries for one normalized key or a deduped set of keys."""
    keys = {lookup_key} if isinstance(lookup_key, str) else lookup_key
    if not keys:
        return []
    entries: dict[tuple[str, str, str], MatchEntry] = {}
    for key in keys:
        rows = conn.execute(
            f"""
            SELECT
                a.mondo_id,
                t.label,
                t.definition,
                a.alias_text,
                a.alias_type,
                a.source_priority
            FROM mondo_aliases a
            JOIN mondo_terms t ON t.mondo_id = a.mondo_id
            WHERE a.normalized_alias = ?
                AND a.alias_type IN ({','.join('?' for _ in alias_types)})
                AND t.deprecated = 0
            """,
            (key, *alias_types),
        )
        for row in rows:
            entry = MatchEntry(
                mondo_id=row['mondo_id'],
                label=row['label'],
                definition=row['definition'],
                matched_text=row['alias_text'],
                match_type=row['alias_type'],
                source_priority=row['source_priority'],
            )
            entries[(entry.mondo_id, entry.match_type, entry.matched_text)] = entry
    return list(entries.values())


def xref_entries_for_lookup(
    conn: sqlite3.Connection,
    lookup_key: str | set[str],
) -> list[MatchEntry]:
    """Return xref entries for one normalized key or a deduped set of keys."""
    keys = {lookup_key} if isinstance(lookup_key, str) else lookup_key
    if not keys:
        return []
    entries: dict[tuple[str, str, str], MatchEntry] = {}
    for key in keys:
        rows = conn.execute(
            """
            SELECT
                x.mondo_id,
                t.label,
                t.definition,
                x.identifier,
                x.xref_type
            FROM mondo_xrefs x
            JOIN mondo_terms t ON t.mondo_id = x.mondo_id
            WHERE x.normalized_identifier = ?
                AND t.deprecated = 0
            """,
            (key,),
        )
        for row in rows:
            entry = MatchEntry(
                mondo_id=row['mondo_id'],
                label=row['label'],
                definition=row['definition'],
                matched_text=row['identifier'],
                match_type=row['xref_type'],
                source_priority=1,
            )
            entries[(entry.mondo_id, entry.match_type, entry.matched_text)] = entry
    return list(entries.values())


def select_unique_entry(
    match_type: str,
    query: str,
    entries: list[MatchEntry],
) -> tuple[MatchEntry | None, dict[str, Any] | None]:
    """Select a match only when all entries point to one MONDO ID."""
    if not entries:
        return None, None
    by_mondo_id = {entry.mondo_id: entry for entry in entries}
    if len(by_mondo_id) == 1:
        return next(iter(by_mondo_id.values())), None
    return None, {
        'match_type': match_type,
        'query': query,
        'candidates': [
            entry.context()
            for entry in sorted(by_mondo_id.values(), key=lambda e: e.mondo_id)
        ],
    }


def term_from_entry(entry: MatchEntry, match_type: str, query: str) -> MondoTerm:
    """Convert a deterministic match entry into the public result model."""
    term = MondoTerm(
        mondo_id=entry.mondo_id,
        term=entry.label,
        match_type=match_type,
        matched_text=entry.matched_text,
        score=100.0,
    )
    term.match_context = build_match_context(
        query=query,
        selected=term,
        candidates=[],
        strict_ambiguities=[],
        agent_used=False,
    )
    term.match_context.update(
        {
            'match_type': match_type,
            'matched_text': entry.matched_text,
        }
    )
    return term


def build_match_context(
    query: str,
    selected: MondoTerm,
    candidates: list[MondoCandidate],
    strict_ambiguities: list[dict[str, Any]],
    agent_used: bool,
    agent_reasoning: str | None = None,
    candidates_considered: list[str] | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    """Build JSON-compatible MONDO linking evidence."""
    selected_context: dict[str, Any] = {
        'mondo_id': selected.mondo_id,
        'term': selected.term,
        'matched_text': selected.matched_text,
        'match_type': selected.match_type,
    }
    if selected.score is not None:
        selected_context['confidence_score'] = float(selected.score)
    if confidence:
        selected_context['confidence'] = confidence

    context: dict[str, Any] = {
        'query': query,
        'normalized_query': normalize_strict(query),
        'selected': selected_context,
        'retrieval': {
            'strategies': ['deterministic_sql', 'trigram_fts', 'rapidfuzz_rerank'],
            'strict_ambiguities': strict_ambiguities,
            'candidates': [candidate.model_dump() for candidate in candidates],
        },
        'agent': {
            'used': agent_used,
        },
    }
    if agent_reasoning:
        context['agent']['reasoning'] = agent_reasoning
    if candidates_considered:
        context['agent']['candidates_considered'] = candidates_considered
    return context


def candidate_to_legacy_context(candidate: MondoCandidate) -> dict[str, Any]:
    """Return the previous fuzzy context shape for compatibility."""
    return {
        'mondo_id': candidate.mondo_id,
        'term': candidate.label,
        'matched_text': candidate.matched_alias_text,
        'match_type': candidate.alias_type,
        'score': candidate.rapidfuzz_score,
    }


def candidate_sort_key(
    candidate: MondoCandidate,
    normalized_query: str,
) -> tuple[float, int, int, str]:
    """Return the deterministic sort key for reranked candidates."""
    return (
        -float(candidate.rapidfuzz_score or 0.0),
        candidate.source_priority,
        abs(len(normalize_fuzzy(candidate.matched_alias_text)) - len(normalized_query)),
        candidate.mondo_id,
    )


def normalize_strict(text: str) -> str:
    """Normalize text for deterministic exact matching."""
    normalized = unicodedata.normalize('NFKC', text)
    normalized = STRICT_DASHES_RE.sub('-', normalized)
    normalized = normalized.strip().strip('"\'')
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.casefold()


def normalize_fuzzy(text: str) -> str:
    """Normalize text for token-based fuzzy matching."""
    normalized = unicodedata.normalize('NFKC', text)
    normalized = STRICT_DASHES_RE.sub('-', normalized)
    normalized = normalized.casefold()
    normalized = FUZZY_PUNCTUATION_RE.sub(' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def normalize_mondo_id(value: str) -> str | None:
    """Return a canonical MONDO CURIE from a MONDO CURIE or IRI-like value."""
    match = MONDO_ID_RE.match(value.strip())
    if not match:
        return None
    return f'MONDO:{match.group(1)}'


def extract_mondo_ids(text: str) -> set[str]:
    """Extract canonical MONDO CURIEs embedded in free text."""
    return {f'MONDO:{match.group(1)}' for match in MONDO_ID_IN_TEXT_RE.finditer(text)}


def iri_to_mondo_id(iri: str) -> str | None:
    """Return a canonical MONDO CURIE from a MONDO OBO IRI."""
    if not isinstance(iri, str):
        return None
    if not iri.startswith(MONDO_IRI_PREFIX):
        return normalize_mondo_id(iri)
    return f'MONDO:{iri.removeprefix(MONDO_IRI_PREFIX)}'


def extract_identifier_keys(text: str) -> set[str]:
    """Extract normalized external identifier keys from free text."""
    keys = set()
    keys.update(normalize_identifier_keys(text))
    for match in CURIE_IN_TEXT_RE.finditer(text):
        keys.update(normalize_identifier_keys(match.group(0)))
    for match in URL_IN_TEXT_RE.finditer(text):
        keys.update(normalize_identifier_keys(match.group(0)))
    return keys


def normalize_identifier_keys(identifier: str) -> set[str]:
    """Return normalized lookup keys for supported CURIE and URL identifiers."""
    identifier = identifier.strip()
    if not identifier:
        return set()

    keys = set()
    if ':' in identifier or identifier.startswith(('http://', 'https://')):
        keys.add(normalize_strict(identifier))
    obo_match = OBO_IRI_RE.match(identifier)
    if obo_match:
        keys.add(normalize_strict(f'{obo_match.group(1)}:{obo_match.group(2)}'))

    orphanet_match = ORPHANET_IRI_RE.match(identifier)
    if orphanet_match:
        keys.add(normalize_strict(f'Orphanet:{orphanet_match.group(1)}'))

    omim_match = OMIM_IRI_RE.match(identifier)
    if omim_match:
        keys.add(normalize_strict(f'OMIM:{omim_match.group(1)}'))

    identifiers_match = IDENTIFIERS_IRI_RE.match(identifier)
    if identifiers_match:
        namespace = identifiers_match.group(1).lower()
        value = identifiers_match.group(2)
        prefix_by_namespace = {
            'medgen': 'MEDGEN',
            'mesh': 'MESH',
            'snomedct': 'SCTID',
        }
        prefix = prefix_by_namespace.get(namespace, namespace)
        keys.add(normalize_strict(f'{prefix}:{value}'))

    icd_match = ICD_IRI_RE.match(identifier)
    if icd_match:
        keys.add(normalize_strict(f'icd11.foundation:{icd_match.group(1)}'))

    return keys


def extract_definition(node: dict[str, Any]) -> str | None:
    """Extract the first textual definition from OWLGraph node metadata."""
    meta = node.get('meta') or {}
    definition = meta.get('definition')
    if isinstance(definition, dict) and isinstance(definition.get('val'), str):
        return definition['val']
    return None


def is_deprecated_node(node: dict[str, Any]) -> bool:
    """Return whether an ontology node is marked deprecated."""
    meta = node.get('meta') or {}
    return bool(meta.get('deprecated')) or bool(node.get('deprecated'))


def is_excluded_synonym_type(synonym_type: Any) -> bool:
    """Return whether a synonym provenance type should be excluded."""
    if not isinstance(synonym_type, str):
        return False
    return any(token in synonym_type.upper() for token in EXCLUDED_SYNONYM_TYPE_TOKENS)


def connect_index(index: MondoIndex) -> sqlite3.Connection:
    """Open a read-only SQLite connection when possible."""
    if index.sqlite_path.exists():
        conn = sqlite3.connect(
            f'file:{index.sqlite_path}?mode=ro',
            uri=True,
        )
    else:
        conn = sqlite3.connect(index.sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_has_trigram_fts(path: Path) -> bool:
    """Return whether an existing MONDO SQLite index has the FTS table."""
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'mondo_alias_trigram_fts'
            """
        ).fetchone()
        return row is not None
    finally:
        conn.close()
