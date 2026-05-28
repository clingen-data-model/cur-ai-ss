import json
import re
import unicodedata
from dataclasses import dataclass, field
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
OBO_IRI_RE = re.compile(r'https?://purl\.obolibrary\.org/obo/([A-Za-z]+)_(.+)$')
ORPHANET_IRI_RE = re.compile(r'https?://www\.orpha\.net/ORDO/Orphanet_(\d+)$')
OMIM_IRI_RE = re.compile(r'https?://omim\.org/entry/(\d+)$')
IDENTIFIERS_IRI_RE = re.compile(r'https?://identifiers\.org/([^/]+)/(.+)$')
ICD_IRI_RE = re.compile(r'https?://id\.who\.int/icd/entity/(.+)$')

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


class MondoTerm(BaseModel):
    mondo_id: str
    term: str
    match_type: str | None = None
    matched_text: str | None = None
    score: float | None = None
    match_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class MondoRecord:
    mondo_id: str
    iri: str
    label: str


@dataclass(frozen=True)
class MatchEntry:
    mondo_id: str
    label: str
    matched_text: str
    match_type: str
    source_priority: int

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


@dataclass
class MondoIndex:
    records: dict[str, MondoRecord]
    by_iri: dict[str, MatchEntry] = field(default_factory=dict)
    label_index: dict[str, list[MatchEntry]] = field(default_factory=dict)
    exact_synonym_index: dict[str, list[MatchEntry]] = field(default_factory=dict)
    related_synonym_index: dict[str, list[MatchEntry]] = field(default_factory=dict)
    broad_narrow_synonym_index: dict[str, list[MatchEntry]] = field(
        default_factory=dict
    )
    abbreviation_index: dict[str, list[MatchEntry]] = field(default_factory=dict)
    xref_index: dict[str, list[MatchEntry]] = field(default_factory=dict)
    deprecated_replacement_index: dict[str, list[MatchEntry]] = field(
        default_factory=dict
    )
    fuzzy_entries: list[MatchEntry] = field(default_factory=list)
    fuzzy_choices: list[str] = field(default_factory=list)


def ontology_path() -> Path:
    return env.reference_data_dir / 'mondo.json'


def ontology_url() -> str:
    return getattr(env, 'MONDO_ONTOLOGY_URL', MONDO_ONTOLOGY_ENDPOINT)


def download_ontology() -> Path:
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
    path = ontology_path()
    if not path.exists():
        return download_ontology()
    return path


def reset_mondo_index_cache() -> None:
    global _mondo_index
    _mondo_index = None


def get_mondo_index() -> MondoIndex:
    global _mondo_index
    if _mondo_index is None:
        _mondo_index = build_mondo_index(ensure_ontology())
    return _mondo_index


def build_mondo_index(path: Path) -> MondoIndex:
    with open(path) as f:
        data = json.load(f)
    graphs = data.get('graphs') or []
    if not graphs:
        raise RuntimeError(f'MONDO ontology file has no graphs: {path}')

    nodes = graphs[0].get('nodes') or []
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
        mondo_id = iri_to_mondo_id(iri)
        if mondo_id is None:
            continue
        if is_deprecated_node(node):
            deprecated_nodes.append(node)
            continue
        record = MondoRecord(mondo_id=mondo_id, iri=iri, label=label)
        raw_records[mondo_id] = node
        records[mondo_id] = record

    index = MondoIndex(records=records)
    for record in records.values():
        node = raw_records[record.mondo_id]
        entry = MatchEntry(
            mondo_id=record.mondo_id,
            label=record.label,
            matched_text=record.label,
            match_type='primary_label',
            source_priority=0,
        )
        index.by_iri[record.iri.casefold()] = entry
        index.by_iri[record.mondo_id.casefold()] = entry
        index.by_iri[record.mondo_id.replace(':', '_').casefold()] = entry
        _append(index.label_index, normalize_strict(record.label), entry)
        index.fuzzy_entries.append(entry)
        index.fuzzy_choices.append(normalize_fuzzy(record.label))

        meta = node.get('meta') or {}
        for synonym in meta.get('synonyms') or []:
            add_synonym_to_index(index, record, synonym)

        for xref in meta.get('xrefs') or []:
            val = xref.get('val') if isinstance(xref, dict) else None
            if isinstance(val, str):
                add_identifier_to_index(index.xref_index, record, val, 'xref')

        for basic_property in meta.get('basicPropertyValues') or []:
            if not isinstance(basic_property, dict):
                continue
            if basic_property.get('pred') == SKOS_EXACT_MATCH and isinstance(
                basic_property.get('val'), str
            ):
                add_identifier_to_index(
                    index.xref_index,
                    record,
                    basic_property['val'],
                    'exact_mapping_id',
                )

    for node in deprecated_nodes:
        add_deprecated_replacement(index, node)

    return index


def add_synonym_to_index(
    index: MondoIndex, record: MondoRecord, synonym: dict[str, Any]
) -> None:
    val = synonym.get('val')
    pred = synonym.get('pred')
    synonym_type = synonym.get('synonymType')
    if not isinstance(val, str) or not isinstance(pred, str):
        return
    if is_excluded_synonym_type(synonym_type):
        return

    if synonym_type == ABBREVIATION_TYPE:
        entry = MatchEntry(
            mondo_id=record.mondo_id,
            label=record.label,
            matched_text=val,
            match_type='abbreviation',
            source_priority=3,
        )
        _append(index.abbreviation_index, normalize_strict(val), entry)
        return

    match_type: str
    target_index: dict[str, list[MatchEntry]]
    source_priority: int
    include_in_fuzzy = False
    if pred == 'hasExactSynonym':
        match_type = 'exact_synonym'
        target_index = index.exact_synonym_index
        source_priority = 1
        include_in_fuzzy = True
    elif pred == 'hasRelatedSynonym':
        match_type = 'related_synonym'
        target_index = index.related_synonym_index
        source_priority = 2
        include_in_fuzzy = True
    elif pred in {'hasBroadSynonym', 'hasNarrowSynonym'}:
        match_type = pred
        target_index = index.broad_narrow_synonym_index
        source_priority = 4
    else:
        return

    entry = MatchEntry(
        mondo_id=record.mondo_id,
        label=record.label,
        matched_text=val,
        match_type=match_type,
        source_priority=source_priority,
    )
    _append(target_index, normalize_strict(val), entry)
    if include_in_fuzzy:
        index.fuzzy_entries.append(entry)
        index.fuzzy_choices.append(normalize_fuzzy(val))


def add_identifier_to_index(
    target_index: dict[str, list[MatchEntry]],
    record: MondoRecord,
    identifier: str,
    match_type: str,
) -> None:
    entry = MatchEntry(
        mondo_id=record.mondo_id,
        label=record.label,
        matched_text=identifier,
        match_type=match_type,
        source_priority=1,
    )
    for key in normalize_identifier_keys(identifier):
        _append(target_index, key, entry)


def add_deprecated_replacement(index: MondoIndex, node: dict[str, Any]) -> None:
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
        if mondo_id and mondo_id in index.records:
            replacement_ids.append(mondo_id)

    distinct_replacements = sorted(set(replacement_ids))
    if len(distinct_replacements) != 1:
        return

    replacement = index.records[distinct_replacements[0]]
    replacement_entry = MatchEntry(
        mondo_id=replacement.mondo_id,
        label=replacement.label,
        matched_text=node.get('lbl', replacement.label),
        match_type='deprecated_replacement',
        source_priority=5,
    )

    deprecated_texts = set()
    if isinstance(node.get('lbl'), str):
        deprecated_texts.add(node['lbl'])
    mondo_id = iri_to_mondo_id(node.get('id', ''))
    if mondo_id:
        deprecated_texts.add(mondo_id)
        deprecated_texts.add(mondo_id.replace(':', '_'))
    for synonym in meta.get('synonyms') or []:
        val = synonym.get('val') if isinstance(synonym, dict) else None
        if isinstance(val, str):
            deprecated_texts.add(val)

    for text in deprecated_texts:
        entry = MatchEntry(
            mondo_id=replacement_entry.mondo_id,
            label=replacement_entry.label,
            matched_text=text,
            match_type='deprecated_replacement',
            source_priority=replacement_entry.source_priority,
        )
        _append(index.deprecated_replacement_index, normalize_strict(text), entry)


def find_mondo_term_for_disease(disease_name: str) -> MondoTerm | None:
    """Return the selected MONDO term for a plaintext disease name."""
    query = disease_name.strip()
    if not query:
        return None

    index = get_mondo_index()
    strict_ambiguities: list[dict[str, Any]] = []

    direct_match = index.by_iri.get(query.casefold())
    if direct_match is None:
        mondo_id = normalize_mondo_id(query)
        direct_match = index.by_iri.get(mondo_id.casefold()) if mondo_id else None
    if direct_match is not None:
        return term_from_entry(direct_match, 'direct_mondo_id', query)

    strict_steps: list[tuple[str, str | set[str], dict[str, list[MatchEntry]]]] = [
        ('primary_label', normalize_strict(query), index.label_index),
        ('exact_synonym', normalize_strict(query), index.exact_synonym_index),
        ('xref', normalize_identifier_keys(query), index.xref_index),
        ('related_synonym', normalize_strict(query), index.related_synonym_index),
        (
            'broad_narrow_synonym',
            normalize_strict(query),
            index.broad_narrow_synonym_index,
        ),
        ('abbreviation', normalize_strict(query), index.abbreviation_index),
        (
            'deprecated_replacement',
            normalize_strict(query),
            index.deprecated_replacement_index,
        ),
    ]
    for match_type, lookup_key, match_index in strict_steps:
        entries = entries_for_lookup(match_index, lookup_key)
        selected, ambiguity = select_unique_entry(match_type, query, entries)
        if selected is not None:
            return term_from_entry(selected, selected.match_type, query)
        if ambiguity is not None:
            strict_ambiguities.append(ambiguity)

    return fuzzy_match(index, query, strict_ambiguities)


def fuzzy_match(
    index: MondoIndex,
    query: str,
    strict_ambiguities: list[dict[str, Any]],
    limit: int = 10,
) -> MondoTerm | None:
    if not index.fuzzy_choices:
        return None

    normalized_query = normalize_fuzzy(query)
    matches = process.extract(
        normalized_query,
        index.fuzzy_choices,
        scorer=fuzz.token_sort_ratio,
        limit=max(limit * 10, 50),
        score_cutoff=0.0,
    )

    best_by_mondo_id: dict[str, tuple[MatchEntry, float]] = {}
    for _, score, entry_idx in matches:
        entry = index.fuzzy_entries[entry_idx]
        existing = best_by_mondo_id.get(entry.mondo_id)
        if existing is None or fuzzy_sort_key(
            entry, score, normalized_query
        ) < fuzzy_sort_key(existing[0], existing[1], normalized_query):
            best_by_mondo_id[entry.mondo_id] = (entry, float(score))

    if not best_by_mondo_id:
        return None

    ranked = sorted(
        best_by_mondo_id.values(),
        key=lambda item: fuzzy_sort_key(item[0], item[1], normalized_query),
    )
    selected, selected_score = ranked[0]
    nearest = [entry.context(score=score) for entry, score in ranked[:limit]]
    context: dict[str, Any] = {
        'query': query,
        'normalized_query': normalized_query,
        'scorer': 'rapidfuzz.fuzz.token_sort_ratio',
        'selected_score': float(selected_score),
        'selected_matched_text': selected.matched_text,
        'selected_match_type': selected.match_type,
        'nearest_candidates': nearest,
    }
    if strict_ambiguities:
        context['strict_ambiguities'] = strict_ambiguities

    return MondoTerm(
        mondo_id=selected.mondo_id,
        term=selected.label,
        match_type='fuzzy',
        matched_text=selected.matched_text,
        score=float(selected_score),
        match_context=context,
    )


def fuzzy_sort_key(
    entry: MatchEntry,
    score: float,
    normalized_query: str,
) -> tuple[float, int, int, str]:
    return (
        -float(score),
        entry.source_priority,
        abs(len(normalize_fuzzy(entry.matched_text)) - len(normalized_query)),
        entry.mondo_id,
    )


def select_unique_entry(
    match_type: str,
    query: str,
    entries: list[MatchEntry],
) -> tuple[MatchEntry | None, dict[str, Any] | None]:
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
    context = {
        'query': query,
        'match_type': match_type,
        'matched_text': entry.matched_text,
    }
    return MondoTerm(
        mondo_id=entry.mondo_id,
        term=entry.label,
        match_type=match_type,
        matched_text=entry.matched_text,
        score=100.0,
        match_context=context,
    )


def entries_for_lookup(
    match_index: dict[str, list[MatchEntry]], lookup_key: str | set[str]
) -> list[MatchEntry]:
    if isinstance(lookup_key, str):
        return match_index.get(lookup_key, [])

    entries_by_mondo_and_type: dict[tuple[str, str, str], MatchEntry] = {}
    for key in lookup_key:
        for entry in match_index.get(key, []):
            entries_by_mondo_and_type[
                (entry.mondo_id, entry.match_type, entry.matched_text)
            ] = entry
    return list(entries_by_mondo_and_type.values())


def normalize_strict(text: str) -> str:
    normalized = unicodedata.normalize('NFKC', text)
    normalized = STRICT_DASHES_RE.sub('-', normalized)
    normalized = normalized.strip().strip('"\'')
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.casefold()


def normalize_fuzzy(text: str) -> str:
    normalized = unicodedata.normalize('NFKC', text)
    normalized = STRICT_DASHES_RE.sub('-', normalized)
    normalized = normalized.casefold()
    normalized = FUZZY_PUNCTUATION_RE.sub(' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def normalize_mondo_id(value: str) -> str | None:
    match = MONDO_ID_RE.match(value.strip())
    if not match:
        return None
    return f'MONDO:{match.group(1)}'


def iri_to_mondo_id(iri: str) -> str | None:
    if not iri.startswith(MONDO_IRI_PREFIX):
        return normalize_mondo_id(iri)
    return f'MONDO:{iri.removeprefix(MONDO_IRI_PREFIX)}'


def normalize_identifier_keys(identifier: str) -> set[str]:
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


def is_deprecated_node(node: dict[str, Any]) -> bool:
    meta = node.get('meta') or {}
    return bool(meta.get('deprecated')) or bool(node.get('deprecated'))


def is_excluded_synonym_type(synonym_type: Any) -> bool:
    if not isinstance(synonym_type, str):
        return False
    return any(token in synonym_type.upper() for token in EXCLUDED_SYNONYM_TYPE_TOKENS)


def _append(lookup: dict[str, list[MatchEntry]], key: str, entry: MatchEntry) -> None:
    if not key:
        return
    lookup.setdefault(key, []).append(entry)
