"""MONDO ontology loading for agent tools."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import requests
from rapidfuzz import fuzz, process

from lib.core.environment import env
from lib.models.mondo import (
    MondoCandidate,
    MondoMatchEvidence,
    MondoSynonym,
    MondoSynonymScope,
    MondoTerm,
    MondoTermDetail,
)

MONDO_IRI_PREFIX = 'http://purl.obolibrary.org/obo/MONDO_'
SKOS_EXACT_MATCH = 'http://www.w3.org/2004/02/skos/core#exactMatch'

MONDO_ID_RE = re.compile(
    r'^(?:https?://purl\.obolibrary\.org/obo/)?MONDO[:_](\d+)$',
    re.IGNORECASE,
)
ORPHANET_IRI_RE = re.compile(r'https?://(?:www\.)?orpha\.net/ORDO/Orphanet_(\d+)$')
OMIM_IRI_RE = re.compile(r'https?://omim\.org/entry/(\d+)$')
IDENTIFIERS_IRI_RE = re.compile(r'https?://identifiers\.org/([^/]+)/(.+)$')
OBO_IRI_RE = re.compile(r'https?://purl\.obolibrary\.org/obo/([A-Za-z]+)_(.+)$')
PUNCTUATION_RE = re.compile(r'[\W_]+')

_mondo_index: 'MondoIndex | None' = None


@dataclass(frozen=True)
class MondoRecord:
    mondo_id: str
    label: str
    definition: str | None = None
    synonyms: list[MondoSynonym] = field(default_factory=list)
    xrefs: list[str] = field(default_factory=list)
    exact_matches: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MondoSearchAlias:
    mondo_id: str
    text: str
    normalized_text: str
    type: Literal['label', 'synonym']
    synonym_scope: MondoSynonymScope | None = None
    synonym_type: str | None = None


@dataclass
class MondoIndex:
    """In-memory lookup structures built from the MONDO ontology.

    Values below are truncated values from MONDO:0007947 (Marfan syndrome).

    MondoIndex
    ├── terms_by_id:       'MONDO:0007947' ──► MondoRecord(label='Marfan syndrome',
    │                                                      definition=..., synonyms=['MFS', ...],
    │                                                      xrefs=['OMIM:154700', ...],
    │                                                      exact_matches=['omim:154700', ...])
    ├── identifier_to_ids: 'omim:154700'   ──► ['MONDO:0007947']   (xref/CURIE → terms)
    │                      'orphanet:558'  ──► ['MONDO:0007947']
    ├── search_aliases:    [MondoSearchAlias(text='Marfan syndrome', type='label',
    │                                         normalized_text='marfan syndrome', mondo_id='MONDO:0007947'),
    │                       MondoSearchAlias(text='MFS', type='synonym',
    │                                         normalized_text='mfs', mondo_id='MONDO:0007947'),
    │                       MondoSearchAlias(text='Marfan syndrome, type 1', type='synonym',
    │                                         normalized_text='marfan syndrome type 1', mondo_id='MONDO:0007947'),
    │                       MondoSearchAlias(text="Marfan's syndrome", type='synonym',
    │                                         normalized_text='marfan s syndrome', mondo_id='MONDO:0007947'), ...]
    │                                          one row per label/synonym (normalized for fuzzy search)
    ├── parent_ids_by_id:  'MONDO:0007947' ──► ['MONDO:0005172', 'MONDO:0017310', ...]  (is-a parents)
    │                                          (skeletal system disorder, Marfan-related disorder)
    └── child_ids_by_id:   'MONDO:0007947' ──► ['MONDO:0017309']  (inverse of parents)
                                               (neonatal Marfan syndrome)
    """

    terms_by_id: dict[str, MondoRecord]
    identifier_to_ids: dict[str, list[str]] = field(default_factory=dict)
    search_aliases: list[MondoSearchAlias] = field(default_factory=list)
    parent_ids_by_id: dict[str, list[str]] = field(default_factory=dict)
    child_ids_by_id: dict[str, list[str]] = field(default_factory=dict)


def _ontology_path() -> Path:
    """Return the local path for the MONDO ontology JSON file."""
    return env.reference_data_dir / 'mondo.json'


def _ontology_url() -> str:
    """Return the configured MONDO ontology download URL."""
    return env.MONDO_ONTOLOGY_URL


def _download_ontology() -> Path:
    """Download the MONDO ontology JSON file to the local reference-data path."""
    path = _ontology_path()
    tmp_path = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(_ontology_url(), stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(tmp_path, 'wb') as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    tmp_path.replace(path)
    return path


def _ensure_ontology() -> Path:
    """Return the local MONDO ontology path, downloading it if needed."""
    path = _ontology_path()
    if path.exists():
        return path
    return _download_ontology()


def _get_mondo_index() -> MondoIndex:
    """Return the process-local MONDO index, building it on first use."""
    global _mondo_index
    if _mondo_index is None:
        _mondo_index = _build_mondo_index(_ensure_ontology())
    return _mondo_index


def _build_mondo_index(path: Path) -> MondoIndex:
    """Build tool-oriented MONDO lookup structures from OWLGraph JSON.

    Args:
        path: Path to the MONDO OWLGraph JSON ontology file.

    Returns:
        A cached index for direct term lookup, xref lookup, fuzzy search, and
        parent/child traversal.
    """
    with open(path) as fh:
        data = json.load(fh)

    graphs = data.get('graphs') or []
    if not graphs:
        raise RuntimeError(f'MONDO ontology file has no graphs: {path}')

    graph = graphs[0]
    terms_by_id: dict[str, MondoRecord] = {}
    index = MondoIndex(terms_by_id=terms_by_id)

    for node in graph.get('nodes') or []:
        mondo_id = _normalize_mondo_curie(node.get('id', ''))
        label = node.get('lbl')
        if (
            mondo_id is None
            or node.get('type') != 'CLASS'
            or not isinstance(label, str)
            or _is_deprecated_node(node)
        ):
            continue

        meta = node.get('meta') or {}
        record = MondoRecord(
            mondo_id=mondo_id,
            label=label,
            definition=_extract_definition(node),
            synonyms=_extract_synonyms(node),
            xrefs=_extract_xrefs(meta.get('xrefs') or []),
            exact_matches=_extract_exact_matches(meta.get('basicPropertyValues') or []),
        )
        terms_by_id[mondo_id] = record

    # Build exact identifier lookup and fuzzy label/synonym search aliases.
    for record in terms_by_id.values():
        _add_search_alias(
            index,
            mondo_id=record.mondo_id,
            text=record.label,
            alias_type='label',
        )
        _add_identifier(index, record.mondo_id, record.mondo_id)
        for xref in record.xrefs:
            _add_identifier(index, xref, record.mondo_id)
        for exact_match in record.exact_matches:
            _add_identifier(index, exact_match, record.mondo_id)
        for synonym in record.synonyms:
            _add_search_alias(
                index,
                mondo_id=record.mondo_id,
                text=synonym.text,
                alias_type='synonym',
                synonym_scope=synonym.scope,
                synonym_type=synonym.synonym_type,
            )
            for xref in synonym.xrefs:
                _add_identifier(index, xref, record.mondo_id)

    # Build one-hop is_a relation maps for parent/child exploration tools.
    for edge in graph.get('edges') or []:
        if edge.get('pred') != 'is_a':
            continue
        child_id = _normalize_mondo_curie(edge.get('sub', ''))
        parent_id = _normalize_mondo_curie(edge.get('obj', ''))
        if child_id not in terms_by_id or parent_id not in terms_by_id:
            continue
        _append_unique(index.parent_ids_by_id.setdefault(child_id, []), parent_id)
        _append_unique(index.child_ids_by_id.setdefault(parent_id, []), child_id)

    return index


def get_mondo_term(
    mondo_id: str,
    include_relations: bool = True,
) -> dict[str, Any] | None:
    """Fetch a MONDO term by CURIE, OBO IRI, or underscore ID."""
    normalized_id = _normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return None
    index = _get_mondo_index()
    record = index.terms_by_id.get(normalized_id)
    if record is None:
        return None
    return _term_payload(record, index=index, include_relations=include_relations)


def search_mondo_terms(
    query: str,
    limit: int = 10,
    score_cutoff: float = 20.0,
) -> list[dict[str, Any]]:
    """Search MONDO labels and synonyms for agent retrieval.

    A single MONDO term contributes many aliases (its label plus every
    synonym), so fuzzy matching runs over aliases and is then collapsed to one
    candidate per term. We over-fetch a pool of ``10 * limit`` alias matches
    before collapsing so that a term whose best alias ranks well is not dropped
    just because lower-scoring aliases of other terms filled the result set;
    after grouping by ``mondo_id`` we return the top ``limit`` terms. This
    mirrors the HPO search in ``lib/reference_data/hpo.py``.

    Args:
        query: Free-text disease query to search.
        limit: Maximum candidates (distinct MONDO terms) to return.
        score_cutoff: Minimum fuzzy match score for raw alias matches.

    Returns:
        Candidate MONDO terms grouped with label/synonym match evidence.
    """
    index = _get_mondo_index()
    normalized_query = _normalize_for_search(query)
    if not normalized_query or limit <= 0:
        return []

    aliases = index.search_aliases
    if not aliases:
        return []
    alias_text = lambda value: (
        value.normalized_text if isinstance(value, MondoSearchAlias) else str(value)
    )

    matches = process.extract(
        normalized_query,
        aliases,
        processor=alias_text,
        scorer=fuzz.token_sort_ratio,
        # Over-fetch aliases; collapsed to `limit` distinct terms below.
        limit=10 * limit,
        score_cutoff=score_cutoff,
    )
    candidates_by_id: dict[str, MondoCandidate] = {}
    for alias, score, _ in matches:
        record = index.terms_by_id[alias.mondo_id]
        candidate = candidates_by_id.get(record.mondo_id)
        if candidate is None:
            candidate = MondoCandidate(
                mondo_id=record.mondo_id,
                label=record.label,
                definition=record.definition,
                score=float(score),
            )
            candidates_by_id[record.mondo_id] = candidate
        else:
            candidate.score = max(candidate.score, float(score))

        candidate.matches.append(_match_evidence(alias, score))

    candidates = list(candidates_by_id.values())
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return [candidate.model_dump(mode='json') for candidate in candidates[:limit]]


def _add_search_alias(
    index: MondoIndex,
    *,
    mondo_id: str,
    text: str,
    alias_type: Literal['label', 'synonym'],
    synonym_scope: MondoSynonymScope | None = None,
    synonym_type: str | None = None,
) -> None:
    """Add an alias to the search mapping if it has searchable text."""
    normalized_text = _normalize_for_search(text)
    if not normalized_text:
        return
    index.search_aliases.append(
        MondoSearchAlias(
            mondo_id=mondo_id,
            text=text,
            normalized_text=normalized_text,
            type=alias_type,
            synonym_scope=synonym_scope,
            synonym_type=synonym_type,
        )
    )


def _match_evidence(alias: MondoSearchAlias, score: float) -> MondoMatchEvidence:
    """Build one search match evidence row from an alias."""
    if alias.type == 'synonym':
        return MondoMatchEvidence(
            text=alias.text,
            normalized_text=alias.normalized_text,
            type='synonym',
            synonym_scope=alias.synonym_scope,
            synonym_type=alias.synonym_type,
            score=float(score),
        )
    return MondoMatchEvidence(
        text=alias.text,
        normalized_text=alias.normalized_text,
        type='label',
        score=float(score),
    )


def get_mondo_by_identifier(identifier: str) -> list[dict[str, Any]]:
    """Fetch MONDO terms by MONDO ID, OBO IRI, xref, or exactMatch identifier."""
    index = _get_mondo_index()
    key = _normalize_identifier_key(identifier)
    if not key:
        return []
    return [
        _term_payload(index.terms_by_id[mondo_id], index=index)
        for mondo_id in index.identifier_to_ids.get(key, [])
        if mondo_id in index.terms_by_id
    ]


def get_mondo_parents(mondo_id: str) -> list[dict[str, Any]]:
    """Fetch parent MONDO terms."""
    index = _get_mondo_index()
    return _get_mondo_related_terms(mondo_id, index.parent_ids_by_id, index)


def get_mondo_children(mondo_id: str) -> list[dict[str, Any]]:
    """Fetch child MONDO terms."""
    index = _get_mondo_index()
    return _get_mondo_related_terms(mondo_id, index.child_ids_by_id, index)


def _get_mondo_related_terms(
    mondo_id: str,
    related_ids_by_id: dict[str, list[str]],
    index: MondoIndex,
) -> list[dict[str, Any]]:
    """Fetch MONDO terms from a precomputed relationship map."""
    normalized_id = _normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return []
    return [
        _term_payload(
            index.terms_by_id[related_id], index=index, include_relations=False
        )
        for related_id in related_ids_by_id.get(normalized_id, [])
        if related_id in index.terms_by_id
    ]


def _term_payload(
    record: MondoRecord,
    index: MondoIndex | None = None,
    include_relations: bool = True,
) -> dict[str, Any]:
    """Convert an indexed MONDO record to a tool payload."""
    return MondoTermDetail(
        mondo_id=record.mondo_id,
        label=record.label,
        definition=record.definition,
        synonyms=record.synonyms,
        xrefs=record.xrefs,
        exact_matches=record.exact_matches,
        parents=_related_term_summaries(
            index.parent_ids_by_id.get(record.mondo_id, []) if index else [],
            index,
        )
        if include_relations
        else [],
        children=_related_term_summaries(
            index.child_ids_by_id.get(record.mondo_id, []) if index else [],
            index,
        )
        if include_relations
        else [],
    ).model_dump(mode='json')


def _related_term_summaries(
    related_ids: list[str],
    index: MondoIndex | None,
) -> list[MondoTerm]:
    """Build compact summaries for related MONDO terms."""
    if index is None:
        return []
    return [
        MondoTerm(
            mondo_id=related_id,
            label=index.terms_by_id[related_id].label,
        )
        for related_id in related_ids
        if related_id in index.terms_by_id
    ]


def _extract_definition(node: dict[str, Any]) -> str | None:
    """Extract a MONDO node definition string."""
    definition = (node.get('meta') or {}).get('definition')
    if not isinstance(definition, dict):
        return None
    val = definition.get('val')
    return val if isinstance(val, str) else None


def _extract_synonyms(node: dict[str, Any]) -> list[MondoSynonym]:
    """Extract structured synonym metadata from a MONDO node."""
    synonyms: list[MondoSynonym] = []
    for synonym in (node.get('meta') or {}).get('synonyms') or []:
        if not isinstance(synonym, dict):
            continue
        val = synonym.get('val')
        if isinstance(val, str):
            _append_unique(
                synonyms,
                MondoSynonym(
                    text=val,
                    scope=_synonym_scope_from_predicate(synonym.get('pred')),
                    synonym_type=_normalize_synonym_type(synonym.get('synonymType')),
                    xrefs=[
                        xref
                        for xref in synonym.get('xrefs') or []
                        if isinstance(xref, str)
                    ],
                ),
            )
    return synonyms


def _extract_xrefs(values: list[Any]) -> list[str]:
    """Extract xref identifier strings from MONDO metadata."""
    xrefs: list[str] = []
    for xref in values:
        val = xref.get('val') if isinstance(xref, dict) else None
        if isinstance(val, str):
            _append_unique(xrefs, val)
    return xrefs


def _extract_exact_matches(values: list[Any]) -> list[str]:
    """Extract exactMatch identifier strings from MONDO metadata."""
    exact_matches: list[str] = []
    for value in values:
        if not isinstance(value, dict) or value.get('pred') != SKOS_EXACT_MATCH:
            continue
        val = value.get('val')
        if isinstance(val, str):
            _append_unique(exact_matches, val)
    return exact_matches


def _add_identifier(index: MondoIndex, identifier: str, mondo_id: str) -> None:
    """Add a MONDO or external identifier to the identifier lookup table."""
    key = _normalize_identifier_key(identifier)
    if not key:
        return
    _append_unique(index.identifier_to_ids.setdefault(key, []), mondo_id)


def _synonym_scope_from_predicate(value: Any) -> MondoSynonymScope:
    """Map a MONDO synonym predicate to a broad evidence scope."""
    if not isinstance(value, str):
        return MondoSynonymScope.UNKNOWN
    predicate = value.lower()
    if predicate.endswith('hasexactsynonym'):
        return MondoSynonymScope.EXACT
    if predicate.endswith('hasrelatedsynonym'):
        return MondoSynonymScope.RELATED
    if predicate.endswith('hasbroadsynonym'):
        return MondoSynonymScope.BROAD
    if predicate.endswith('hasnarrowsynonym'):
        return MondoSynonymScope.NARROW
    return MondoSynonymScope.UNKNOWN


def _normalize_synonym_type(value: Any) -> str | None:
    """Return a compact synonym type label from a MONDO synonym type IRI."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for separator in ('#', '/'):
        if separator in text:
            text = text.rsplit(separator, 1)[-1]
    return text or None


def _normalize_mondo_curie(value: str) -> str | None:
    """Normalize a MONDO CURIE, OBO IRI, or underscore ID."""
    if not isinstance(value, str):
        return None
    match = MONDO_ID_RE.match(value.strip())
    if not match:
        return None
    return f'MONDO:{match.group(1)}'


def _normalize_identifier_key(identifier: str) -> str:
    """Normalize common external identifier formats for xref lookup."""
    value = _normalize_text(identifier)
    if not value:
        return ''

    mondo_id = _normalize_mondo_curie(value)
    if mondo_id is not None:
        return mondo_id.lower()

    for regex, prefix in (
        (ORPHANET_IRI_RE, 'orphanet'),
        (OMIM_IRI_RE, 'omim'),
        (IDENTIFIERS_IRI_RE, None),
        (OBO_IRI_RE, None),
    ):
        match = regex.match(value)
        if not match:
            continue
        if prefix is not None:
            return f'{prefix}:{match.group(1).lower()}'
        prefix_part = match.group(1).lower()
        if prefix_part == 'orpha':
            prefix_part = 'orphanet'
        return f'{prefix_part}:{match.group(2).lower()}'

    if ':' in value:
        prefix_part, suffix = value.split(':', 1)
        if prefix_part.lower() == 'orpha':
            prefix_part = 'orphanet'
        return f'{prefix_part.lower()}:{suffix.lower()}'
    return value.lower()


def _normalize_for_search(value: str) -> str:
    """Normalize disease text for fuzzy retrieval."""
    normalized = _normalize_text(value).lower()
    normalized = PUNCTUATION_RE.sub(' ', normalized)
    return ' '.join(normalized.split())


def _normalize_text(value: str) -> str:
    """Normalize Unicode and whitespace while preserving punctuation.

    Strip external whitespace, collapse internal whitespace,
    and apply Unicode NFKC normalization.

    Example:
        ``_normalize_text('  Marfan\\u00a0syndrome (Orphanet:558)  ')`` returns
        ``'Marfan syndrome (Orphanet:558)'``.
    """
    normalized = unicodedata.normalize('NFKC', value or '')
    return ' '.join(normalized.strip().split())


def _is_deprecated_node(node: dict[str, Any]) -> bool:
    """Return whether a MONDO node is marked deprecated."""
    meta = node.get('meta') or {}
    if meta.get('deprecated') is True:
        return True
    for value in meta.get('basicPropertyValues') or []:
        if not isinstance(value, dict):
            continue
        if value.get('pred') == 'http://www.w3.org/2002/07/owl#deprecated':
            return str(value.get('val')).lower() == 'true'
    return False


def _append_unique(values: list[Any], value: Any) -> None:
    """Append a value only if an equal value is not already present."""
    if value not in values:
        values.append(value)
