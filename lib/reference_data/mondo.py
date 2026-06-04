"""MONDO ontology loading and disease-name matching.

Disease names come from paper and patient-variant extraction agents, so most
inputs are author-facing text rather than ontology IDs. The matcher therefore
tries high-confidence deterministic lookups before fuzzy matching. The order is
intentional: direct MONDO IDs and primary labels are strongest, synonyms and
external IDs require more source-aware handling, abbreviations are often
ambiguous, and deprecated terms should resolve only through explicit
replacement metadata. Fuzzy matching is a final fallback for typos, punctuation
differences, and near labels, with context stored for audit.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel
from rapidfuzz import fuzz, process

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

_mondo_index: 'MondoIndex | None' = None


class MondoMatchType(StrEnum):
    DIRECT_MONDO_ID = 'direct_mondo_id'
    PRIMARY_LABEL = 'primary_label'
    EXACT_SYNONYM = 'exact_synonym'
    XREF = 'xref'
    EXACT_MAPPING_ID = 'exact_mapping_id'
    RELATED_SYNONYM = 'related_synonym'
    BROAD_SYNONYM = 'hasBroadSynonym'
    NARROW_SYNONYM = 'hasNarrowSynonym'
    BROAD_NARROW_SYNONYM = 'broad_narrow_synonym'
    ABBREVIATION = 'abbreviation'
    DEPRECATED_REPLACEMENT = 'deprecated_replacement'
    AGENT_SELECTED = 'agent_selected'


class MondoTerm(BaseModel):
    mondo_id: str
    term: str
    match_type: MondoMatchType | None = None
    matched_text: str | None = None


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
    alias_type: MondoMatchType
    definition: str | None = None
    rapidfuzz_score: float | None = None


@dataclass(frozen=True)
class MondoRecord:
    mondo_id: str
    label: str
    definition: str | None = None
    aliases: list[str] = field(default_factory=list)
    xrefs: list[str] = field(default_factory=list)


@dataclass
class MondoIndex:
    records: dict[str, MondoRecord]
    label_index: dict[str, list[str]] = field(default_factory=dict)
    exact_synonym_index: dict[str, list[str]] = field(default_factory=dict)
    related_synonym_index: dict[str, list[str]] = field(default_factory=dict)
    broad_synonym_index: dict[str, list[str]] = field(default_factory=dict)
    narrow_synonym_index: dict[str, list[str]] = field(default_factory=dict)
    abbreviation_index: dict[str, list[str]] = field(default_factory=dict)
    xref_index: dict[str, list[str]] = field(default_factory=dict)
    exact_mapping_index: dict[str, list[str]] = field(default_factory=dict)
    deprecated_replacement_index: dict[str, list[str]] = field(default_factory=dict)
    fuzzy_choices: list[str] = field(default_factory=list)
    fuzzy_choice_to_mondo_ids: dict[str, list[str]] = field(default_factory=dict)
    fuzzy_choice_match_types: dict[str, MondoMatchType] = field(default_factory=dict)
    parent_edges_by_mondo_id: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict
    )
    child_edges_by_mondo_id: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict
    )


def ontology_path() -> Path:
    """Return the local path for the MONDO ontology JSON file."""
    return env.reference_data_dir / 'mondo.json'


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


def get_mondo_index() -> MondoIndex:
    """Return the process-local MONDO index, building it on first use."""
    global _mondo_index
    if _mondo_index is None:
        _mondo_index = build_mondo_index(ensure_ontology())
    return _mondo_index


def build_mondo_index(path: Path) -> MondoIndex:
    """Build lookup tables from OWLGraph JSON nodes.

    For now this loads the entire mondo JSON file using json.loads and prunes it
    down, however the dict from json.loads must fit into memory (400-500MiB).

    Non-deprecated MONDO CLASS nodes become records keyed by CURIE. Separate
    lookup maps connect normalized primary labels, synonym text by predicate,
    abbreviation text, and external IDs from node xrefs / exactMatch properties
    to MONDO IDs. Deprecated nodes are kept out of normal indexes and only
    contribute replacement lookups when they point to one valid non-deprecated
    MONDO term. Text keys use strict normalization for deterministic matching;
    fuzzy choices retain original alias/xref text and use looser
    punctuation/whitespace normalization at query time.

    Args:
        path: Path to the MONDO OWLGraph JSON ontology file.

    Returns:
        A MondoIndex containing deterministic lookup indexes and fuzzy choices.
    """
    with open(path) as f:
        data = json.load(f)
    graphs = data.get('graphs') or []
    if not graphs:
        raise RuntimeError(f'MONDO ontology file has no graphs: {path}')

    graph = graphs[0]
    nodes = graph.get('nodes') or []
    edges = graph.get('edges') or []
    raw_records: dict[str, dict[str, Any]] = {}
    records: dict[str, MondoRecord] = {}
    deprecated_nodes: list[dict[str, Any]] = []

    for node in nodes:
        iri = node.get('id')
        label = node.get('lbl')
        if not isinstance(iri, str) or not iri.startswith(MONDO_IRI_PREFIX):
            continue
        if node.get('type') != 'CLASS' or not isinstance(label, str):
            continue
        mondo_id = normalize_mondo_curie(iri)
        if mondo_id is None:
            continue
        if is_deprecated_node(node):
            deprecated_nodes.append(node)
            continue
        record = MondoRecord(
            mondo_id=mondo_id,
            label=label,
            definition=extract_definition(node),
            aliases=[label],
        )
        raw_records[mondo_id] = node
        records[mondo_id] = record

    index = MondoIndex(records=records)
    for record in records.values():
        node = raw_records[record.mondo_id]
        _append_id(index.label_index, normalize_strict(record.label), record.mondo_id)
        add_fuzzy_choice(
            index, record.label, record.mondo_id, MondoMatchType.PRIMARY_LABEL
        )

        meta = node.get('meta') or {}
        for synonym in meta.get('synonyms') or []:
            add_synonym_to_index(index, record, synonym)

        for xref in meta.get('xrefs') or []:
            val = xref.get('val') if isinstance(xref, dict) else None
            if isinstance(val, str):
                add_identifier_to_index(index, record, val, MondoMatchType.XREF)

        for basic_property in meta.get('basicPropertyValues') or []:
            if not isinstance(basic_property, dict):
                continue
            if basic_property.get('pred') == SKOS_EXACT_MATCH and isinstance(
                basic_property.get('val'), str
            ):
                add_identifier_to_index(
                    index,
                    record,
                    basic_property['val'],
                    MondoMatchType.EXACT_MAPPING_ID,
                )

    for node in deprecated_nodes:
        add_deprecated_replacement(index, node)

    for edge in edges:
        add_edge_to_index(index, edge)

    return index


def add_synonym_to_index(
    index: MondoIndex, record: MondoRecord, synonym: dict[str, Any]
) -> None:
    """Add a MONDO synonym to the appropriate exact and fuzzy indexes.

    Synonyms with excluded provenance types are ignored. Abbreviations are kept
    in their own exact-only index because they are often ambiguous. Exact and
    related synonyms are also added to the fuzzy candidate lists; broad and
    narrow synonyms remain exact-only because their semantic relationship is
    weaker.
    """
    val = synonym.get('val')
    pred = synonym.get('pred')
    synonym_type = synonym.get('synonymType')
    if not isinstance(val, str) or not isinstance(pred, str):
        return
    if is_excluded_synonym_type(synonym_type):
        return
    _append_unique(record.aliases, val)

    if synonym_type == ABBREVIATION_TYPE:
        _append_id(
            index.abbreviation_index,
            normalize_strict(val),
            record.mondo_id,
        )
        return

    match_type: MondoMatchType
    target_index: dict[str, list[str]]
    include_in_fuzzy = False
    if pred == 'hasExactSynonym':
        match_type = MondoMatchType.EXACT_SYNONYM
        target_index = index.exact_synonym_index
        include_in_fuzzy = True
    elif pred == 'hasRelatedSynonym':
        match_type = MondoMatchType.RELATED_SYNONYM
        target_index = index.related_synonym_index
        include_in_fuzzy = True
    elif pred == MondoMatchType.BROAD_SYNONYM:
        match_type = MondoMatchType.BROAD_SYNONYM
        target_index = index.broad_synonym_index
    elif pred == MondoMatchType.NARROW_SYNONYM:
        match_type = MondoMatchType.NARROW_SYNONYM
        target_index = index.narrow_synonym_index
    else:
        return

    _append_id(target_index, normalize_strict(val), record.mondo_id)
    if include_in_fuzzy:
        add_fuzzy_choice(index, val, record.mondo_id, match_type)


def add_identifier_to_index(
    index: MondoIndex,
    record: MondoRecord,
    identifier: str,
    match_type: MondoMatchType,
) -> None:
    """Add normalized lookup keys for an external identifier mapping."""
    target_index = (
        index.exact_mapping_index
        if match_type == MondoMatchType.EXACT_MAPPING_ID
        else index.xref_index
    )
    key = normalize_identifier_key(identifier)
    if key is not None:
        _append_id(target_index, key, record.mondo_id)
    _append_unique(record.xrefs, identifier)
    add_fuzzy_choice(index, identifier, record.mondo_id, match_type)


def add_deprecated_replacement(index: MondoIndex, node: dict[str, Any]) -> None:
    """Index deprecated node text when it has one valid MONDO replacement.

    Replacement metadata is accepted only when it resolves to exactly one
    non-deprecated MONDO record already present in the index. When that is true,
    the deprecated label, deprecated MONDO ID forms, and deprecated synonyms are
    indexed as exact lookups that return the current replacement term.
    """
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
        mondo_id = normalize_mondo_curie(val)
        if mondo_id and mondo_id in index.records:
            replacement_ids.append(mondo_id)

    distinct_replacements = sorted(set(replacement_ids))
    if len(distinct_replacements) != 1:
        return

    replacement = index.records[distinct_replacements[0]]
    deprecated_texts = set()
    if isinstance(node.get('lbl'), str):
        deprecated_texts.add(node['lbl'])
    mondo_id = normalize_mondo_curie(node.get('id', ''))
    if mondo_id:
        deprecated_texts.add(mondo_id)
        deprecated_texts.add(mondo_id.replace(':', '_'))
    for synonym in meta.get('synonyms') or []:
        val = synonym.get('val') if isinstance(synonym, dict) else None
        if isinstance(val, str):
            deprecated_texts.add(val)

    for text in deprecated_texts:
        _append_id(
            index.deprecated_replacement_index,
            normalize_strict(text),
            replacement.mondo_id,
        )


def add_edge_to_index(index: MondoIndex, edge: dict[str, Any]) -> None:
    """Add one parent/child MONDO edge to the in-memory graph indexes."""
    subject = normalize_mondo_curie(edge.get('sub', ''))
    obj = normalize_mondo_curie(edge.get('obj', ''))
    pred = edge.get('pred')
    if not subject or not obj or not isinstance(pred, str):
        return
    if subject not in index.records or obj not in index.records:
        return

    parent = index.records[obj]
    child = index.records[subject]
    index.parent_edges_by_mondo_id.setdefault(subject, []).append(
        {
            'mondo_id': parent.mondo_id,
            'label': parent.label,
            'definition': parent.definition,
            'predicate': pred,
        }
    )
    index.child_edges_by_mondo_id.setdefault(obj, []).append(
        {
            'mondo_id': child.mondo_id,
            'label': child.label,
            'definition': child.definition,
            'predicate': pred,
        }
    )


def deterministic_index_lookup(
    index: MondoIndex,
    query: str,
) -> tuple[MondoTerm | None, list[dict[str, Any]]]:
    """Return an exact MONDO match or ambiguity context from in-memory indexes."""
    strict_ambiguities: list[dict[str, Any]] = []

    # A MONDO ID embedded in the query is the strongest deterministic signal.
    # records is already keyed by canonical MONDO CURIE, so no text index is needed.
    mondo_ids_in_query = [
        mondo_id
        for mondo_id in extract_mondo_curies(query)
        if mondo_id in index.records
    ]
    selected, ambiguity = unique_mondo_id_or_ambiguity(
        index,
        MondoMatchType.DIRECT_MONDO_ID,
        query,
        mondo_ids_in_query,
    )
    if selected is not None:
        return (
            term_from_mondo_id(
                index,
                selected,
                MondoMatchType.DIRECT_MONDO_ID,
                query,
                matched_text=selected,
            ),
            strict_ambiguities,
        )
    if ambiguity is not None:
        strict_ambiguities.append(ambiguity)

    # Try exact text/identifier indexes from highest-confidence to weakest.
    # Each lookup map is keyed by normalized input text and points to MONDO IDs.
    strict_steps: list[tuple[MondoMatchType, str | set[str], dict[str, list[str]]]] = [
        (MondoMatchType.PRIMARY_LABEL, normalize_strict(query), index.label_index),
        (
            MondoMatchType.EXACT_SYNONYM,
            normalize_strict(query),
            index.exact_synonym_index,
        ),
        (MondoMatchType.XREF, extract_identifier_keys(query), index.xref_index),
        (
            MondoMatchType.EXACT_MAPPING_ID,
            extract_identifier_keys(query),
            index.exact_mapping_index,
        ),
        (
            MondoMatchType.RELATED_SYNONYM,
            normalize_strict(query),
            index.related_synonym_index,
        ),
        (
            MondoMatchType.BROAD_SYNONYM,
            normalize_strict(query),
            index.broad_synonym_index,
        ),
        (
            MondoMatchType.NARROW_SYNONYM,
            normalize_strict(query),
            index.narrow_synonym_index,
        ),
        (
            MondoMatchType.ABBREVIATION,
            normalize_strict(query),
            index.abbreviation_index,
        ),
        (
            MondoMatchType.DEPRECATED_REPLACEMENT,
            normalize_strict(query),
            index.deprecated_replacement_index,
        ),
    ]
    for match_type, lookup_key, match_index in strict_steps:
        mondo_ids = mondo_ids_for_lookup(match_index, lookup_key)
        selected, ambiguity = unique_mondo_id_or_ambiguity(
            index, match_type, query, mondo_ids
        )
        if selected is not None:
            return term_from_mondo_id(
                index, selected, match_type, query
            ), strict_ambiguities
        if ambiguity is not None:
            # Keep ambiguity evidence and continue; a later, weaker tier should
            # not override it, but it may provide useful agent context.
            strict_ambiguities.append(ambiguity)

    if strict_ambiguities:
        return None, strict_ambiguities

    return None, []


def _rank_rapidfuzz_matches(
    index: MondoIndex,
    query: str,
    limit: int,
) -> list[tuple[str, str, MondoMatchType, float]]:
    """Return RapidFuzz-ranked matches with at most one alias per MONDO ID."""
    # Exit early if the query has no text to match against after normalization
    if not normalize_fuzzy(query):
        return []

    matches = process.extract(
        query,
        index.fuzzy_choices,
        scorer=fuzz.token_sort_ratio,
        limit=max(limit * 10, 50),
        processor=normalize_fuzzy,
    )

    # RapidFuzz ranks aliases; keep the first alias seen for each MONDO term.
    ranked: list[tuple[str, str, MondoMatchType, float]] = []
    seen_mondo_ids: set[str] = set()
    for choice, score, _ in matches:
        match_type = index.fuzzy_choice_match_types[choice]
        for mondo_id in index.fuzzy_choice_to_mondo_ids[choice]:
            if mondo_id in seen_mondo_ids:
                continue
            seen_mondo_ids.add(mondo_id)
            ranked.append((mondo_id, choice, match_type, float(score)))
            if len(ranked) >= limit:
                return ranked

    return ranked


def retrieve_mondo_fuzzy_candidates(
    index: MondoIndex,
    query: str,
    limit: int = 20,
) -> list[MondoCandidate]:
    """Return RapidFuzz-ranked candidates from in-memory fuzzy aliases."""
    ranked = _rank_rapidfuzz_matches(index, query, limit=limit)
    return [
        MondoCandidate(
            mondo_id=mondo_id,
            label=index.records[mondo_id].label,
            definition=index.records[mondo_id].definition,
            matched_alias_text=choice,
            alias_type=match_type,
            rapidfuzz_score=float(score),
        )
        for mondo_id, choice, match_type, score in ranked
    ]


def unique_mondo_id_or_ambiguity(
    index: MondoIndex,
    match_type: MondoMatchType,
    query: str,
    mondo_ids: list[str],
) -> tuple[str | None, dict[str, Any] | None]:
    """Select a match only when all IDs point to one MONDO ID.

    Args:
        index: The MONDO ontology index.
        match_type: Lookup tier that produced the entries.
        query: Original user-facing disease query.
        mondo_ids: Candidate MONDO IDs for the lookup tier.

    Returns:
        A selected MONDO ID and no ambiguity context when the tier is
        unambiguous; otherwise no ID plus ambiguity context when multiple MONDO
        IDs match. If there are no IDs, both return values are None.
    """
    if not mondo_ids:
        return None, None

    distinct_ids = sorted(set(mondo_ids))
    if len(distinct_ids) == 1:
        return distinct_ids[0], None

    return None, {
        'match_type': match_type,
        'query': query,
        'candidates': [
            match_context(index, mondo_id, match_type, query)
            for mondo_id in distinct_ids
        ],
    }


def term_from_mondo_id(
    index: MondoIndex,
    mondo_id: str,
    match_type: MondoMatchType,
    query: str,
    matched_text: str | None = None,
) -> MondoTerm:
    """Convert a deterministic MONDO ID match into the public result model."""
    record = index.records[mondo_id]
    return MondoTerm(
        mondo_id=record.mondo_id,
        term=record.label,
        match_type=match_type,
        matched_text=matched_text or query,
    )


def get_mondo_term(mondo_id: str) -> dict[str, Any] | None:
    """Return MONDO term details for tools and agent validation."""
    normalized_id = normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return None
    index = get_mondo_index()
    record = index.records.get(normalized_id)
    if record is None:
        return None
    aliases = [
        {'alias_text': alias}
        for alias in sorted(set(record.aliases), key=lambda alias: alias.casefold())
    ]
    xrefs = [
        {'identifier': xref}
        for xref in sorted(set(record.xrefs), key=lambda xref: xref.casefold())
    ]
    return {
        'mondo_id': record.mondo_id,
        'iri': mondo_id_to_iri(record.mondo_id),
        'label': record.label,
        'definition': record.definition,
        'deprecated': False,
        'replacement_mondo_id': None,
        'aliases': aliases,
        'xrefs': xrefs,
    }


def get_mondo_related_terms(mondo_id: str, direction: str) -> list[dict[str, Any]]:
    """Return parent or child MONDO terms connected by ontology edges."""
    normalized_id = normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return []
    index = get_mondo_index()
    if direction == 'parents':
        related = index.parent_edges_by_mondo_id.get(normalized_id, [])
    else:
        related = index.child_edges_by_mondo_id.get(normalized_id, [])
    return sorted(related, key=lambda row: row['label'])[:100]


def get_mondo_terms_by_xref(identifier: str) -> list[dict[str, Any]]:
    """Return MONDO terms matching an external identifier."""
    index = get_mondo_index()
    keys = extract_identifier_keys(identifier)
    if not keys:
        return []
    matches: dict[tuple[str, MondoMatchType], str] = {}
    for match_type, match_index in (
        (MondoMatchType.XREF, index.xref_index),
        (MondoMatchType.EXACT_MAPPING_ID, index.exact_mapping_index),
    ):
        for mondo_id in mondo_ids_for_lookup(match_index, keys):
            matches[(mondo_id, match_type)] = identifier

    return [
        {
            'mondo_id': record.mondo_id,
            'label': record.label,
            'definition': record.definition,
            'matched_identifier': matched_identifier,
            'xref_type': match_type,
        }
        for (matched_id, match_type), matched_identifier in sorted(matches.items())
        if (record := index.records.get(matched_id)) is not None
    ]


def build_agent_match_context(
    query: str,
    selected: MondoTerm,
    fuzzy_candidates: list[MondoCandidate],
    strict_ambiguities: list[dict[str, Any]],
    agent_reasoning: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    """Build JSON-compatible evidence for an agent-selected MONDO match."""
    selected_context = selected.model_dump(mode='json', exclude_none=True)
    if confidence:
        selected_context['confidence'] = confidence

    context: dict[str, Any] = {
        'query': query,
        'normalized_query': {
            'strict': normalize_strict(query),
            'fuzzy': normalize_fuzzy(query),
        },
        'selected': selected_context,
        'strict_ambiguities': strict_ambiguities,
        'fuzzy_candidates': [candidate.model_dump() for candidate in fuzzy_candidates],
    }
    if agent_reasoning:
        context['agent_reasoning'] = agent_reasoning
    return context


def mondo_ids_for_lookup(
    match_index: dict[str, list[str]], lookup_key: str | set[str]
) -> list[str]:
    """Return MONDO IDs for one normalized key or a deduped set of keys."""
    if isinstance(lookup_key, str):
        return match_index.get(lookup_key, [])

    mondo_ids = set()
    for key in lookup_key:
        mondo_ids.update(match_index.get(key, []))
    return sorted(mondo_ids)


def match_context(
    index: MondoIndex,
    mondo_id: str,
    match_type: MondoMatchType,
    matched_text: str,
) -> dict[str, Any]:
    """Return serializable audit context for a match candidate."""
    record = index.records[mondo_id]
    return {
        'mondo_id': record.mondo_id,
        'term': record.label,
        'matched_text': matched_text,
        'match_type': match_type,
    }


def fuzzy_match_type_priority(match_type: MondoMatchType) -> int:
    """Return deterministic tie-break priority for fuzzy match categories."""
    priority_by_type = {
        MondoMatchType.PRIMARY_LABEL: 0,
        MondoMatchType.EXACT_SYNONYM: 1,
        MondoMatchType.XREF: 1,
        MondoMatchType.EXACT_MAPPING_ID: 1,
        MondoMatchType.RELATED_SYNONYM: 2,
    }
    return priority_by_type.get(match_type, 99)


def normalize_strict(text: str) -> str:
    """Normalize text for deterministic exact matching.

    Preserves punctuation and token boundaries while folding Unicode, dash
    variants, surrounding quotes, repeated whitespace, and case.
    """
    normalized = unicodedata.normalize('NFKC', text)
    normalized = STRICT_DASHES_RE.sub('-', normalized)
    normalized = normalized.strip().strip('"\'')
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.casefold()


def normalize_fuzzy(text: str) -> str:
    """Normalize text for token-based fuzzy matching.

    Folds Unicode, dashes, and case, then converts punctuation and
    underscores to spaces so RapidFuzz compares token content.
    """
    normalized = unicodedata.normalize('NFKC', text)
    normalized = STRICT_DASHES_RE.sub('-', normalized)
    normalized = normalized.casefold()
    normalized = FUZZY_PUNCTUATION_RE.sub(' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def normalize_mondo_curie(value: str) -> str | None:
    """Return a canonical MONDO CURIE from a MONDO CURIE or IRI-like value."""
    if not isinstance(value, str):
        return None
    if value.startswith(MONDO_IRI_PREFIX):
        return f'MONDO:{value.removeprefix(MONDO_IRI_PREFIX)}'
    match = MONDO_ID_RE.match(value.strip())
    if not match:
        return None
    return f'MONDO:{match.group(1)}'


def extract_mondo_curies(text: str) -> set[str]:
    """Extract canonical MONDO CURIEs embedded in free text."""
    return {f'MONDO:{match.group(1)}' for match in MONDO_ID_IN_TEXT_RE.finditer(text)}


def extract_identifier_keys(text: str) -> set[str]:
    """Extract normalized external identifier keys from free text.

    Checks the whole input first, then scans for embedded CURIE and URL tokens
    so identifier-only strings and prose containing identifiers both match.
    """
    keys = set()
    if key := normalize_identifier_key(text):
        keys.add(key)
    for match in CURIE_IN_TEXT_RE.finditer(text):
        if key := normalize_identifier_key(match.group(0)):
            keys.add(key)
    for match in URL_IN_TEXT_RE.finditer(text):
        if key := normalize_identifier_key(match.group(0)):
            keys.add(key)
    return keys


def normalize_identifier_key(identifier: str) -> str | None:
    """Return a canonical lookup key for a supported CURIE or URL identifier.

    Supported OBO, Orphanet, OMIM, identifiers.org, and ICD URLs are converted
    to equivalent CURIE-style keys. Unrecognized CURIE or URL values fall back
    to their normalized input form.
    """
    identifier = identifier.strip()
    if not identifier:
        return None

    obo_match = OBO_IRI_RE.match(identifier)
    if obo_match:
        return normalize_strict(f'{obo_match.group(1)}:{obo_match.group(2)}')

    orphanet_match = ORPHANET_IRI_RE.match(identifier)
    if orphanet_match:
        return normalize_strict(f'Orphanet:{orphanet_match.group(1)}')

    omim_match = OMIM_IRI_RE.match(identifier)
    if omim_match:
        return normalize_strict(f'OMIM:{omim_match.group(1)}')

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
        return normalize_strict(f'{prefix}:{value}')

    icd_match = ICD_IRI_RE.match(identifier)
    if icd_match:
        return normalize_strict(f'icd11.foundation:{icd_match.group(1)}')

    if ':' in identifier or identifier.startswith(('http://', 'https://')):
        return normalize_strict(identifier)
    return None


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


def mondo_id_to_iri(mondo_id: str) -> str:
    """Return the canonical OBO IRI for a MONDO CURIE."""
    return f'{MONDO_IRI_PREFIX}{mondo_id.removeprefix("MONDO:")}'


def add_fuzzy_choice(
    index: MondoIndex,
    choice: str,
    mondo_id: str,
    match_type: MondoMatchType,
) -> None:
    """Add one RapidFuzz choice and its MONDO ID mapping.

    The same alias text can point to multiple MONDO IDs with different match
    types. For example, Record A may have "foo syndrome" as a related synonym
    while Record B has "foo syndrome" as its primary label. Keep all MONDO IDs,
    but retain the strongest observed match type for the shared choice text.
    """
    if not choice:
        return
    if choice not in index.fuzzy_choice_to_mondo_ids:
        index.fuzzy_choices.append(choice)
        index.fuzzy_choice_to_mondo_ids[choice] = []
        index.fuzzy_choice_match_types[choice] = match_type
    elif fuzzy_match_type_priority(match_type) < fuzzy_match_type_priority(
        index.fuzzy_choice_match_types[choice]
    ):
        index.fuzzy_choice_match_types[choice] = match_type
    _append_unique(index.fuzzy_choice_to_mondo_ids[choice], mondo_id)


def _append_id(lookup: dict[str, list[str]], key: str, mondo_id: str) -> None:
    """Append a MONDO ID to a lookup list when the key is non-empty."""
    if not key:
        return
    _append_unique(lookup.setdefault(key, []), mondo_id)


def _append_unique(values: list[str], value: str) -> None:
    """Append a string only if it is not already present."""
    if value not in values:
        values.append(value)
