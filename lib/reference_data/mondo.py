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


class MondoDiseaseScope(StrEnum):
    """Disease text scope for MONDO linking tasks."""

    PAPER = 'paper'
    OCCURRENCE = 'occurrence'


class MondoTerm(BaseModel):
    """A compact MONDO term payload for agent tools."""

    mondo_id: str
    label: str
    definition: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    xrefs: list[str] = Field(default_factory=list)
    exact_matches: list[str] = Field(default_factory=list)


class MondoCandidate(BaseModel):
    """A MONDO search candidate returned to the agent."""

    mondo_id: str
    label: str
    matched_text: str
    matched_text_type: MondoAliasType
    definition: str | None = None
    score: float


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
    synonyms: list[str] = field(default_factory=list)
    xrefs: list[str] = field(default_factory=list)
    exact_matches: list[str] = field(default_factory=list)


@dataclass
class MondoIndex:
    terms_by_id: dict[str, MondoRecord]
    xref_to_ids: dict[str, list[str]] = field(default_factory=dict)
    fuzzy_choices: list[str] = field(default_factory=list)
    fuzzy_choice_to_terms: dict[str, list[tuple[str, MondoAliasType]]] = field(
        default_factory=dict
    )
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
        add_fuzzy_choice(index, record.label, record.mondo_id, MondoAliasType.LABEL)
        for synonym in record.synonyms:
            add_fuzzy_choice(index, synonym, record.mondo_id, MondoAliasType.SYNONYM)
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


def get_mondo_term(mondo_id: str) -> dict[str, Any] | None:
    """Fetch a MONDO term by CURIE, OBO IRI, or underscore ID."""
    normalized_id = normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return None
    record = get_mondo_index().terms_by_id.get(normalized_id)
    if record is None:
        return None
    return term_payload(record)


def search_mondo_terms(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search MONDO labels and synonyms for agent retrieval.

    Args:
        query: Free-text disease query or normalized variant to search.
        limit: Maximum candidates to return.

    Returns:
        Candidate MONDO terms with the matched alias and retrieval score.
    """
    index = get_mondo_index()
    normalized_query = normalize_for_search(query)
    if not normalized_query:
        return []

    matches = process.extract(
        normalized_query,
        index.fuzzy_choices,
        scorer=fuzz.WRatio,
        limit=max(limit * 4, limit),
    )
    candidates: list[MondoCandidate] = []
    seen_ids: set[str] = set()
    for choice, score, _ in matches:
        for mondo_id, alias_type in index.fuzzy_choice_to_terms.get(choice, []):
            if mondo_id in seen_ids:
                continue
            record = index.terms_by_id[mondo_id]
            candidates.append(
                MondoCandidate(
                    mondo_id=record.mondo_id,
                    label=record.label,
                    matched_text=choice,
                    matched_text_type=alias_type,
                    definition=record.definition,
                    score=float(score),
                )
            )
            seen_ids.add(mondo_id)
            if len(candidates) >= limit:
                return [candidate.model_dump(mode='json') for candidate in candidates]

    return [candidate.model_dump(mode='json') for candidate in candidates]


def get_mondo_terms_by_xref(identifier: str) -> list[dict[str, Any]]:
    """Fetch MONDO terms that reference an external identifier."""
    index = get_mondo_index()
    key = normalize_identifier_key(identifier)
    if not key:
        return []
    return [
        term_payload(index.terms_by_id[mondo_id])
        for mondo_id in index.xref_to_ids.get(key, [])
        if mondo_id in index.terms_by_id
    ]


def get_mondo_related_terms(mondo_id: str, direction: str) -> list[dict[str, Any]]:
    """Fetch parent or child MONDO terms."""
    normalized_id = normalize_mondo_curie(mondo_id)
    if normalized_id is None:
        return []
    index = get_mondo_index()
    if direction == 'parents':
        related_ids = index.parent_ids_by_id.get(normalized_id, [])
    elif direction == 'children':
        related_ids = index.child_ids_by_id.get(normalized_id, [])
    else:
        raise ValueError(f'Unsupported MONDO relation direction: {direction}')
    return [
        term_payload(index.terms_by_id[related_id])
        for related_id in related_ids
        if related_id in index.terms_by_id
    ]


def term_payload(record: MondoRecord) -> dict[str, Any]:
    """Convert an indexed MONDO record to a tool payload."""
    return MondoTerm(
        mondo_id=record.mondo_id,
        label=record.label,
        definition=record.definition,
        synonyms=record.synonyms,
        xrefs=record.xrefs,
        exact_matches=record.exact_matches,
    ).model_dump(mode='json')


def extract_definition(node: dict[str, Any]) -> str | None:
    """Extract a MONDO node definition string."""
    definition = (node.get('meta') or {}).get('definition')
    if not isinstance(definition, dict):
        return None
    val = definition.get('val')
    return val if isinstance(val, str) else None


def extract_synonyms(node: dict[str, Any]) -> list[str]:
    """Extract synonym strings from a MONDO node."""
    synonyms: list[str] = []
    for synonym in (node.get('meta') or {}).get('synonyms') or []:
        if not isinstance(synonym, dict):
            continue
        val = synonym.get('val')
        if isinstance(val, str):
            append_unique(synonyms, val)
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


def add_fuzzy_choice(
    index: MondoIndex,
    text: str,
    mondo_id: str,
    alias_type: MondoAliasType,
) -> None:
    """Add text to the MONDO fuzzy search lookup."""
    choice = normalize_for_search(text)
    if not choice:
        return
    if choice not in index.fuzzy_choice_to_terms:
        index.fuzzy_choices.append(choice)
        index.fuzzy_choice_to_terms[choice] = []
    entry = (mondo_id, alias_type)
    if entry not in index.fuzzy_choice_to_terms[choice]:
        index.fuzzy_choice_to_terms[choice].append(entry)


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
    """Normalize Unicode and whitespace while preserving punctuation."""
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
