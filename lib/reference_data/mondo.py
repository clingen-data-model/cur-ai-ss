"""MONDO ontology loading for agent tools."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process

from lib.core.environment import env

MONDO_ONTOLOGY_ENDPOINT = 'https://purl.obolibrary.org/obo/mondo.json'
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


class MondoAliasType(StrEnum):
    """MONDO text source used to retrieve a candidate."""

    LABEL = 'label'
    SYNONYM = 'synonym'
    XREF = 'xref'
    EXACT_MATCH = 'exact_match'


class MondoSynonymScope(StrEnum):
    """MONDO synonym scope from the synonym predicate."""

    EXACT = 'exact'
    RELATED = 'related'
    BROAD = 'broad'
    NARROW = 'narrow'
    UNKNOWN = 'unknown'


class MondoDiseaseScope(StrEnum):
    """Disease text scope for MONDO linking tasks."""

    PAPER = 'paper'
    OCCURRENCE = 'occurrence'


class MondoSynonym(BaseModel):
    """A structured MONDO synonym."""

    text: str
    scope: MondoSynonymScope = MondoSynonymScope.UNKNOWN
    synonym_type: str | None = None
    xrefs: list[str] = Field(default_factory=list)


class MondoTermSummary(BaseModel):
    """A compact related MONDO term summary."""

    mondo_id: str
    label: str


class MondoTerm(BaseModel):
    """A compact MONDO term payload for agent tools."""

    mondo_id: str
    label: str
    definition: str | None = None
    synonyms: list[MondoSynonym] = Field(default_factory=list)
    xrefs: list[str] = Field(default_factory=list)
    exact_matches: list[str] = Field(default_factory=list)
    parents: list[MondoTermSummary] = Field(default_factory=list)
    children: list[MondoTermSummary] = Field(default_factory=list)


class MondoMatchEvidence(BaseModel):
    """One label or synonym match that supports a MONDO candidate."""

    text: str
    normalized_text: str
    type: MondoAliasType
    score: float
    synonym_scope: MondoSynonymScope | None = None
    synonym_type: str | None = None


class MondoCandidate(BaseModel):
    """A MONDO search candidate returned to the agent."""

    mondo_id: str
    label: str
    definition: str | None = None
    score: float
    matches: list[MondoMatchEvidence] = Field(default_factory=list)


class MondoDiseaseContext(BaseModel):
    """Context supplied to the MONDO linking agent."""

    paper_title: str | None = None
    paper_abstract: str | None = None
    paper_disease_name: str | None = None
    occurrence_disease_text: str | None = None
    gene_symbol: str | None = None
    inheritance_mode: str | None = None


class MondoLinkingTarget(BaseModel):
    """Disease text target for paper- or occurrence-scoped MONDO linking."""

    scope: MondoDiseaseScope
    paper_id: int
    patient_variant_occurrence_id: int | None = None
    disease_text: str | None = None
    context: MondoDiseaseContext = Field(default_factory=MondoDiseaseContext)


@dataclass(frozen=True)
class MondoRecord:
    mondo_id: str
    label: str
    definition: str | None = None
    synonyms: list[MondoSynonym] = field(default_factory=list)
    xrefs: list[str] = field(default_factory=list)
    exact_matches: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MondoAlias:
    mondo_id: str
    text: str
    normalized_text: str
    type: MondoAliasType
    synonym_scope: MondoSynonymScope | None = None
    synonym_type: str | None = None


@dataclass
class MondoIndex:
    terms_by_id: dict[str, MondoRecord]
    xref_to_ids: dict[str, list[str]] = field(default_factory=dict)
    fuzzy_choices: list[str] = field(default_factory=list)
    fuzzy_choice_to_aliases: dict[str, list[MondoAlias]] = field(default_factory=dict)
    parent_ids_by_id: dict[str, list[str]] = field(default_factory=dict)
    child_ids_by_id: dict[str, list[str]] = field(default_factory=dict)


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
    with requests.get(ontology_url(), stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(tmp_path, 'wb') as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    tmp_path.replace(path)
    return path


def ensure_ontology() -> Path:
    """Return the local MONDO ontology path, downloading it if needed."""
    path = ontology_path()
    if path.exists():
        return path
    return download_ontology()


def get_mondo_index() -> MondoIndex:
    """Return the process-local MONDO index, building it on first use."""
    global _mondo_index
    if _mondo_index is None:
        _mondo_index = build_mondo_index(ensure_ontology())
    return _mondo_index


def build_mondo_index(path: Path) -> MondoIndex:
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
        mondo_id = normalize_mondo_curie(node.get('id', ''))
        label = node.get('lbl')
        if (
            mondo_id is None
            or node.get('type') != 'CLASS'
            or not isinstance(label, str)
            or is_deprecated_node(node)
        ):
            continue

        meta = node.get('meta') or {}
        record = MondoRecord(
            mondo_id=mondo_id,
            label=label,
            definition=extract_definition(node),
            synonyms=extract_synonyms(node),
            xrefs=extract_xrefs(meta.get('xrefs') or []),
            exact_matches=extract_exact_matches(meta.get('basicPropertyValues') or []),
        )
        terms_by_id[mondo_id] = record

    for record in terms_by_id.values():
        add_fuzzy_alias(
            index,
            MondoAlias(
                mondo_id=record.mondo_id,
                text=record.label,
                normalized_text=normalize_for_search(record.label),
                type=MondoAliasType.LABEL,
            ),
        )
        for synonym in record.synonyms:
            add_fuzzy_alias(
                index,
                MondoAlias(
                    mondo_id=record.mondo_id,
                    text=synonym.text,
                    normalized_text=normalize_for_search(synonym.text),
                    type=MondoAliasType.SYNONYM,
                    synonym_scope=synonym.scope,
                    synonym_type=synonym.synonym_type,
                ),
            )
        for xref in record.xrefs:
            add_identifier(index, xref, record.mondo_id)
        for exact_match in record.exact_matches:
            add_identifier(index, exact_match, record.mondo_id)

    for edge in graph.get('edges') or []:
        if edge.get('pred') != 'is_a':
            continue
        child_id = normalize_mondo_curie(edge.get('sub', ''))
        parent_id = normalize_mondo_curie(edge.get('obj', ''))
        if child_id not in terms_by_id or parent_id not in terms_by_id:
            continue
        append_unique(index.parent_ids_by_id.setdefault(child_id, []), parent_id)
        append_unique(index.child_ids_by_id.setdefault(parent_id, []), child_id)

    return index


def get_mondo_term(
    mondo_id: str,
    include_relations: bool = True,
) -> dict[str, Any] | None:
    """Fetch a MONDO term by CURIE, OBO IRI, or underscore ID."""
    normalized_id = normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return None
    index = get_mondo_index()
    record = index.terms_by_id.get(normalized_id)
    if record is None:
        return None
    return term_payload(record, index=index, include_relations=include_relations)


def search_mondo_terms(
    query: str,
    limit: int = 10,
    search_labels: bool = True,
    search_synonyms: bool = True,
) -> list[dict[str, Any]]:
    """Search MONDO labels and synonyms for agent retrieval.

    Args:
        query: Free-text disease query or normalized variant to search.
        limit: Maximum candidates to return.
        search_labels: Whether to search preferred labels.
        search_synonyms: Whether to search synonyms.

    Returns:
        Candidate MONDO terms grouped with label/synonym match evidence.
    """
    index = get_mondo_index()
    normalized_query = normalize_for_search(query)
    if not normalized_query or limit <= 0:
        return []

    allowed_alias_types: set[MondoAliasType] = set()
    if search_labels:
        allowed_alias_types.add(MondoAliasType.LABEL)
    if search_synonyms:
        allowed_alias_types.add(MondoAliasType.SYNONYM)
    if not allowed_alias_types:
        return []

    eligible_choices = [
        choice
        for choice in index.fuzzy_choices
        if any(
            alias.type in allowed_alias_types
            for alias in index.fuzzy_choice_to_aliases.get(choice, [])
        )
    ]
    if not eligible_choices:
        return []

    matches = process.extract(
        normalized_query,
        eligible_choices,
        scorer=fuzz.WRatio,
        limit=max(limit * 20, 50),
    )
    candidates_by_id: dict[str, MondoCandidate] = {}
    candidate_order: list[str] = []
    for choice, score, _ in matches:
        for alias in index.fuzzy_choice_to_aliases.get(choice, []):
            if alias.type not in allowed_alias_types:
                continue
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
                candidate_order.append(record.mondo_id)
            else:
                candidate.score = max(candidate.score, float(score))

            evidence = MondoMatchEvidence(
                text=alias.text,
                normalized_text=alias.normalized_text,
                type=alias.type,
                synonym_scope=alias.synonym_scope,
                synonym_type=alias.synonym_type,
                score=float(score),
            )
            if not has_match_evidence(candidate.matches, evidence):
                candidate.matches.append(evidence)

    candidates = list(candidates_by_id.values())
    order_by_id = {mondo_id: order for order, mondo_id in enumerate(candidate_order)}
    candidates.sort(
        key=lambda candidate: (-candidate.score, order_by_id[candidate.mondo_id])
    )
    return [candidate.model_dump(mode='json') for candidate in candidates[:limit]]


def has_match_evidence(
    matches: list[MondoMatchEvidence],
    evidence: MondoMatchEvidence,
) -> bool:
    """Return whether equivalent match evidence is already present."""
    return any(
        match.text == evidence.text
        and match.normalized_text == evidence.normalized_text
        and match.type == evidence.type
        and match.synonym_scope == evidence.synonym_scope
        and match.synonym_type == evidence.synonym_type
        for match in matches
    )


def get_mondo_terms_by_xref(identifier: str) -> list[dict[str, Any]]:
    """Fetch MONDO terms that reference an external identifier."""
    index = get_mondo_index()
    key = normalize_identifier_key(identifier)
    if not key:
        return []
    return [
        term_payload(index.terms_by_id[mondo_id], index=index)
        for mondo_id in index.xref_to_ids.get(key, [])
        if mondo_id in index.terms_by_id
    ]


def get_mondo_parents(mondo_id: str) -> list[dict[str, Any]]:
    """Fetch parent MONDO terms."""
    index = get_mondo_index()
    return _get_mondo_related_terms(mondo_id, index.parent_ids_by_id, index)


def get_mondo_children(mondo_id: str) -> list[dict[str, Any]]:
    """Fetch child MONDO terms."""
    index = get_mondo_index()
    return _get_mondo_related_terms(mondo_id, index.child_ids_by_id, index)


def _get_mondo_related_terms(
    mondo_id: str,
    related_ids_by_id: dict[str, list[str]],
    index: MondoIndex,
) -> list[dict[str, Any]]:
    """Fetch MONDO terms from a precomputed relationship map."""
    normalized_id = normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return []
    return [
        term_payload(
            index.terms_by_id[related_id], index=index, include_relations=False
        )
        for related_id in related_ids_by_id.get(normalized_id, [])
        if related_id in index.terms_by_id
    ]


def term_payload(
    record: MondoRecord,
    index: MondoIndex | None = None,
    include_relations: bool = True,
) -> dict[str, Any]:
    """Convert an indexed MONDO record to a tool payload."""
    return MondoTerm(
        mondo_id=record.mondo_id,
        label=record.label,
        definition=record.definition,
        synonyms=record.synonyms,
        xrefs=record.xrefs,
        exact_matches=record.exact_matches,
        parents=related_term_summaries(
            index.parent_ids_by_id.get(record.mondo_id, []) if index else [],
            index,
        )
        if include_relations
        else [],
        children=related_term_summaries(
            index.child_ids_by_id.get(record.mondo_id, []) if index else [],
            index,
        )
        if include_relations
        else [],
    ).model_dump(mode='json')


def related_term_summaries(
    related_ids: list[str],
    index: MondoIndex | None,
) -> list[MondoTermSummary]:
    """Build compact summaries for related MONDO terms."""
    if index is None:
        return []
    return [
        MondoTermSummary(
            mondo_id=related_id,
            label=index.terms_by_id[related_id].label,
        )
        for related_id in related_ids
        if related_id in index.terms_by_id
    ]


def extract_definition(node: dict[str, Any]) -> str | None:
    """Extract a MONDO node definition string."""
    definition = (node.get('meta') or {}).get('definition')
    if not isinstance(definition, dict):
        return None
    val = definition.get('val')
    return val if isinstance(val, str) else None


def extract_synonyms(node: dict[str, Any]) -> list[MondoSynonym]:
    """Extract structured synonym metadata from a MONDO node."""
    synonyms: list[MondoSynonym] = []
    for synonym in (node.get('meta') or {}).get('synonyms') or []:
        if not isinstance(synonym, dict):
            continue
        val = synonym.get('val')
        if isinstance(val, str):
            append_unique_synonym(
                synonyms,
                MondoSynonym(
                    text=val,
                    scope=synonym_scope_from_predicate(synonym.get('pred')),
                    synonym_type=normalize_synonym_type(synonym.get('synonymType')),
                    xrefs=[
                        xref
                        for xref in synonym.get('xrefs') or []
                        if isinstance(xref, str)
                    ],
                ),
            )
    return synonyms


def extract_xrefs(values: list[Any]) -> list[str]:
    """Extract xref identifier strings from MONDO metadata."""
    xrefs: list[str] = []
    for xref in values:
        val = xref.get('val') if isinstance(xref, dict) else None
        if isinstance(val, str):
            append_unique(xrefs, val)
    return xrefs


def extract_exact_matches(values: list[Any]) -> list[str]:
    """Extract exactMatch identifier strings from MONDO metadata."""
    exact_matches: list[str] = []
    for value in values:
        if not isinstance(value, dict) or value.get('pred') != SKOS_EXACT_MATCH:
            continue
        val = value.get('val')
        if isinstance(val, str):
            append_unique(exact_matches, val)
    return exact_matches


def add_identifier(index: MondoIndex, identifier: str, mondo_id: str) -> None:
    """Add an external identifier to the xref lookup table."""
    key = normalize_identifier_key(identifier)
    if not key:
        return
    append_unique(index.xref_to_ids.setdefault(key, []), mondo_id)


def add_fuzzy_alias(index: MondoIndex, alias: MondoAlias) -> None:
    """Add a label or synonym alias to the MONDO fuzzy search lookup."""
    if not alias.normalized_text:
        return
    if alias.normalized_text not in index.fuzzy_choice_to_aliases:
        index.fuzzy_choices.append(alias.normalized_text)
        index.fuzzy_choice_to_aliases[alias.normalized_text] = []
    if alias not in index.fuzzy_choice_to_aliases[alias.normalized_text]:
        index.fuzzy_choice_to_aliases[alias.normalized_text].append(alias)


def synonym_scope_from_predicate(value: Any) -> MondoSynonymScope:
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


def normalize_synonym_type(value: Any) -> str | None:
    """Return a compact synonym type label from a MONDO synonym type IRI."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for separator in ('#', '/'):
        if separator in text:
            text = text.rsplit(separator, 1)[-1]
    return text or None


def normalize_mondo_curie(value: str) -> str | None:
    """Normalize a MONDO CURIE, OBO IRI, or underscore ID."""
    if not isinstance(value, str):
        return None
    match = MONDO_ID_RE.match(value.strip())
    if not match:
        return None
    return f'MONDO:{match.group(1)}'


def normalize_identifier_key(identifier: str) -> str:
    """Normalize common external identifier formats for xref lookup."""
    value = normalize_text(identifier)
    if not value:
        return ''

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
        return f'{match.group(1).lower()}:{match.group(2).lower()}'

    if ':' in value:
        prefix_part, suffix = value.split(':', 1)
        return f'{prefix_part.lower()}:{suffix.lower()}'
    return value.lower()


def normalize_for_search(value: str) -> str:
    """Normalize disease text for fuzzy retrieval."""
    normalized = normalize_text(value).lower()
    normalized = PUNCTUATION_RE.sub(' ', normalized)
    return ' '.join(normalized.split())


def normalize_text(value: str) -> str:
    """Normalize Unicode and whitespace while preserving punctuation.

    Strip external whitespace, collapse internal whitespace,
    and apply Unicode NFKC normalization.

    Example:
        ``normalize_text('  Marfan\\u00a0syndrome (Orphanet:558)  ')`` returns
        ``'Marfan syndrome (Orphanet:558)'``.
    """
    normalized = unicodedata.normalize('NFKC', value or '')
    return ' '.join(normalized.strip().split())


def is_deprecated_node(node: dict[str, Any]) -> bool:
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


def append_unique(values: list[str], value: str) -> None:
    """Append a value only if it is not already present."""
    if value not in values:
        values.append(value)


def append_unique_synonym(values: list[MondoSynonym], value: MondoSynonym) -> None:
    """Append a synonym only if equivalent metadata is not already present."""
    if value not in values:
        values.append(value)
