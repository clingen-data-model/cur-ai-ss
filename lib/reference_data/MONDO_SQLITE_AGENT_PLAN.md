# MONDO SQLite Retrieval and Agent Adjudication Plan

## Summary

Replace the current in-memory MONDO matcher with a SQLite-backed retrieval layer
and an optional tool-using MONDO agent. Preserve the current import surface where
possible, while moving the old implementation to
`lib/reference_data/mondo_index_strict_fuzz_deterministic.py` for comparison and
fallback during migration.

The new flow is:

1. Run deterministic SQL lookup for high-confidence matches.
2. Generate candidates with SQLite trigram FTS and RapidFuzz reranking.
3. Use an LLM agent only for uncertain, ambiguous, or no-exact-match cases.
4. Store retrieval candidates and agent reasoning in `mondo_match_context`.

## Public Interface

- Rename current `lib/reference_data/mondo.py` to
  `lib/reference_data/mondo_index_strict_fuzz_deterministic.py`.
- Create a new `lib/reference_data/mondo.py` exposing:
  - `find_mondo_term_for_disease(disease_name: str) -> MondoTerm | None`
  - `async find_mondo_term_for_disease_with_agent(disease_name: str, context: MondoDiseaseContext | None = None) -> MondoTerm | None`
- Keep `MondoTerm` compatible with current callers:
  - `mondo_id`
  - `term`
  - `match_type`
  - `matched_text`
  - `score`
  - `match_context`
- Update `handle_mondo_linking` to use the async agent-backed function and pass
  paper or occurrence context when available.

The synchronous function should remain deterministic and non-agent-backed. It is
kept for tests, simple callers, and exact/automatic linking.

## SQLite Reference Index

Build `mondo.sqlite` from `mondo.json` under the configured reference-data
directory. Runtime matching should open SQLite read-only and should not parse
the full ontology JSON unless the SQLite index is missing and needs to be built.

Recommended tables:

- `mondo_terms`
  - `mondo_id`
  - `iri`
  - `label`
  - `definition`
  - `deprecated`
  - `replacement_mondo_id`
- `mondo_aliases`
  - `id`
  - `mondo_id`
  - `alias_text`
  - `normalized_alias`
  - `alias_type`
  - `source_priority`
- `mondo_xrefs`
  - `id`
  - `mondo_id`
  - `identifier`
  - `normalized_identifier`
  - `xref_type`
- `mondo_edges`
  - `subject_mondo_id`
  - `predicate`
  - `object_mondo_id`
- `mondo_alias_trigram_fts`
  - FTS5 table using `tokenize='trigram'` over normalized alias text.

Word-token FTS is useful for evaluation and diagnostics, but it is not required
for the production retrieval path. Exact SQL indexes plus trigram FTS should
cover exact-ish and typo-tolerant candidate retrieval with fewer moving parts.

## Deterministic Matching

Auto-link without an agent when a tier returns exactly one high-confidence
MONDO ID.

Strict tiers:

1. Direct MONDO ID or MONDO IRI.
2. Exact primary label.
3. Exact `hasExactSynonym`.
4. External xref or exact mapping ID.
5. Exact `hasRelatedSynonym`.
6. Exact `hasNarrowSynonym` or `hasBroadSynonym`.
7. Unique abbreviation.
8. Deprecated replacement, only when exactly one valid replacement exists.

Strict text normalization should remain conservative:

- Unicode normalize.
- Case-fold.
- Trim whitespace and surrounding quotes.
- Collapse repeated whitespace.
- Normalize dash variants to `-`.
- Do not remove subtype numbers, gene symbols, inheritance words, or disease
  type tokens.

If a strict tier is ambiguous, record candidates in context and continue to
candidate generation rather than silently choosing.

## Candidate Generation

For uncertain or no-exact-match cases, generate a candidate set from one or more
database-backed passes.

Production default:

1. Query `mondo_alias_trigram_fts` for typo-tolerant candidate aliases.
2. Deduplicate aliases by MONDO ID, keeping source metadata and best alias.
3. Rerank candidates with RapidFuzz `token_sort_ratio`.
4. Apply deterministic tie-breakers:
   - higher RapidFuzz score
   - stronger source priority
   - closer normalized length
   - stable MONDO ID sort

Evaluation mode may additionally compare:

- word-token FTS
- trigram FTS
- exhaustive RapidFuzz over all aliases
- combined retrieval strategies

The production path should store enough candidate metadata to explain why the
agent saw each candidate:

- MONDO ID
- label
- matched alias text
- alias type
- retrieval source
- FTS rank or score when available
- RapidFuzz score when available

## MONDO Agent

Add `lib/agents/mondo_linking_agent.py` using the same `openai-agents` pattern
as the HPO linker.

Tools:

- `search_mondo_terms(query: str, strategy: str = "combined", limit: int = 20) -> list[dict]`
- `get_mondo_term(mondo_id: str) -> dict`
- `get_mondo_parents(mondo_id: str) -> list[dict]`
- `get_mondo_children(mondo_id: str) -> list[dict]`
- `get_mondo_by_xref(identifier: str) -> list[dict]`

The agent receives:

- disease string
- initial candidates
- paper title or abstract when available
- gene symbol when available
- inheritance mode when available
- occurrence-level disease text when available

The agent returns a structured decision:

- selected `mondo_id` and term, or null
- confidence
- matched text
- match type
- candidates considered
- concise reasoning

Agent rules:

- Never invent a MONDO ID.
- Select only a term returned by candidate generation or tools.
- Prefer null over a weak guess.
- Use paper context only to disambiguate supported candidates, not to infer
  unsupported disease specificity.
- Verify selected terms with `get_mondo_term` before finalizing.

## Evidence Structure

Store a JSON-compatible evidence object in `MondoTerm.match_context`, persisted
to `mondo_match_context`.

Recommended shape:

```json
{
  "query": "moruio syndrome",
  "normalized_query": "moruio syndrome",
  "selected": {
    "mondo_id": "MONDO:0018938",
    "term": "Morquio syndrome",
    "matched_text": "Morquio syndrome",
    "match_type": "agent_selected",
    "confidence": "high"
  },
  "retrieval": {
    "strategies": ["deterministic_sql", "trigram_fts", "rapidfuzz_rerank"],
    "strict_ambiguities": [],
    "candidates": []
  },
  "agent": {
    "used": true,
    "reasoning": "The query appears to be a misspelling of Morquio syndrome; the selected MONDO term is the closest supported candidate.",
    "candidates_considered": ["MONDO:0018938", "MONDO:0009647"]
  }
}
```

For deterministic auto-links, `agent.used` should be false or omitted.

## Evaluation CLI

Add an evaluation CLI separate from production matching:

```bash
uv run python scripts/evaluate_mondo_retrieval.py --sample-size 1000
uv run python scripts/evaluate_mondo_retrieval.py --query "moruio syndrome"
uv run python scripts/evaluate_mondo_retrieval.py --strategies trigram_fts,rapidfuzz,combined
```

The CLI should report recall at K for:

- exact normalized aliases
- punctuation variants
- typo variants
- dropped-token variants
- reordered-token variants
- targeted typo cases where a generic token such as `disease` or `syndrome`
  remains

It should print concrete miss examples with RapidFuzz and FTS rankings.

## Test Plan

- Unit tests for SQLite index building from small MONDO JSON fixtures.
- Unit tests for deterministic SQL tiers matching current expected behavior.
- Retrieval tests showing:
  - trigram FTS recovers typo cases.
  - RapidFuzz reranking preserves expected top candidates.
  - combined retrieval deduplicates by MONDO ID and keeps source metadata.
- Agent tests with mocked tool outputs and mocked final decisions.
- Handler tests confirming `mondo_match_context` persists candidates and agent
  reasoning.
- Regression tests against current deterministic behavior in
  `test/reference_data/test_mondo.py`.

## Assumptions

- Exact unambiguous matches do not require an LLM call.
- The async agent-backed function is used by MONDO task handlers.
- SQLite FTS5 trigram tokenizer is available in the deployed Python SQLite
  build. If unavailable, record the strategy as disabled and fall back to
  RapidFuzz candidate generation.
- The old strict/fuzzy implementation remains importable for migration
  comparison, but production imports continue through `lib.reference_data.mondo`.
