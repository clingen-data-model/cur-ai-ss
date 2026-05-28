# MONDO Disease Term Matching Implementation Plan

## Summary

Implement `find_mondo_term_for_disease(disease_name: str) -> MondoTerm | None`
in `lib/reference_data/mondo.py` using the deterministic tiers from
`MONDO_MATCHING_STRATEGY.md`, then fall back to fuzzy matching when strict
matching does not produce one usable MONDO term.

The matcher will use `env.reference_data_dir / "mondo.json"` by default and
index non-deprecated MONDO disease nodes. It will not attempt to identify
human-only terms or exclude non-human/cross-species records in v1.

## Key Changes

- Extend `MondoTerm` with optional audit fields while preserving current callers:
  - `mondo_id: str`
  - `term: str`
  - `match_type: str | None`
  - `matched_text: str | None`
  - `score: float | None`
  - `match_context: dict | None`
- Add nullable JSON DB/API field on both disease-bearing records:
  - `papers.mondo_match_context`
  - `patient_variant_occurrences.mondo_match_context`
- Update `handle_mondo_linking` to persist `mondo_id`, `mondo_term`, and
  `mondo_match_context`.
- Strict matches may have minimal context.
- Fuzzy matches must include score and nearest-candidate context.

## Matcher Behavior

- Load and cache a `MondoIndex` from `reference_data/mondo.json`.
- Index only nodes whose IDs start with
  `http://purl.obolibrary.org/obo/MONDO_`.
- Exclude deprecated nodes from normal indexes.
- Do not exclude nodes based on species labels or cross-species metadata. Rare
  non-human false matches are accepted in v1 and can be corrected from stored
  match context/manual edits.
- Build separate indexes for:
  - MONDO CURIE/IRI IDs
  - normalized primary labels from `node.lbl`
  - normalized synonym text from `meta.synonyms[*].val`, grouped by predicate
  - abbreviation synonyms
  - external identifiers from `node.meta.xrefs`
  - exact mapping IDs from relevant `meta.basicPropertyValues`
  - deprecated terms and their replacement metadata

Strict matching order:

1. Direct MONDO ID or MONDO IRI.
2. Exact primary label.
3. Exact `hasExactSynonym`.
4. External identifier/xref, such as `OMIM:...`, `GARD:...`, `Orphanet:...`,
   `DOID:...`.
5. Exact `hasRelatedSynonym`.
6. Exact `hasNarrowSynonym` / `hasBroadSynonym`.
7. Unique abbreviation synonym.
8. Deprecated term replacement, only when exactly one valid replacement exists.

Strict text normalization:

- Unicode normalize.
- `casefold()`.
- Trim whitespace.
- Collapse repeated whitespace.
- Normalize dash variants to `-`.
- Strip surrounding quotes.
- Do not remove subtype numbers, gene symbols, inheritance words, or disease
  type tokens.

Strict ambiguity handling:

- If a strict tier produces exactly one distinct MONDO ID, return it.
- If a strict tier produces multiple distinct MONDO IDs, record those candidates
  in context and continue to later tiers/fuzzy matching.
- Do not use `synonym.xrefs` as match strings; they are synonym provenance only.
- Use `node.meta.xrefs` only for identifier matching, not text matching.

Fuzzy fallback:

- Run only after strict matching fails to select one term.
- Use RapidFuzz `token_sort_ratio`, matching the existing HPO implementation
  style.
- Fuzzy index includes primary labels, `hasExactSynonym`, and
  `hasRelatedSynonym`.
- Exclude abbreviations, broad/narrow synonyms, deprecated synonyms,
  ambiguous/dubious synonyms, and misspelling synonyms from fuzzy matching.
- Fuzzy normalization may be looser than strict normalization: convert
  hyphens/slashes/punctuation to spaces and collapse whitespace.
- Always select the top distinct MONDO candidate when fuzzy matching runs.
- Store fuzzy audit context with:
  - normalized query
  - scorer name
  - selected score
  - selected matched text/source
  - top nearest distinct MONDO candidates, including IDs, labels, matched text,
    match type/source, and scores
  - any prior strict ambiguities

Tie breaking for fuzzy candidates:

1. Higher RapidFuzz score.
2. Source priority: primary label, exact synonym, related synonym.
3. Smaller length difference from normalized query.
4. Stable MONDO ID sort.

## Test Plan

- Unit tests for strict matching:
  - Direct `MONDO:...` and MONDO IRI.
  - Exact primary label.
  - Exact synonym value.
  - Related synonym value, e.g. `limb-girdle muscular dystrophy type 2Q`.
  - External xref ID, e.g. `GARD:0016535` maps to Marfan syndrome.
  - Confirm xref IDs are not treated as text labels.
  - Unique abbreviation resolves; ambiguous abbreviation does not resolve via
    strict abbreviation.
  - Deprecated term with one replacement resolves to replacement.
  - Human disease names containing animal words, e.g. `cat eye syndrome`, remain
    matchable.
  - Cross-species MONDO nodes are indexed if they are otherwise valid
    non-deprecated MONDO classes.
- Unit tests for fuzzy fallback:
  - Typo/plural examples such as `cystic fibroses`.
  - Punctuation examples such as `sickle-cell anemia`.
  - Fuzzy result includes selected score and nearest candidates.
  - Fuzzy top candidate is deterministic under tied or near-tied scores.
- Pipeline/API tests:
  - `handle_mondo_linking` persists `mondo_match_context` for paper and
    occurrence disease names.
  - API responses expose `mondo_match_context`.
  - Existing mocked `MondoTerm(mondo_id=..., term=...)` tests still pass because
    new fields are optional.
- Migration checks:
  - Alembic upgrade adds nullable JSON context fields.
  - Alembic downgrade removes them.

## Assumptions

- `reference_data/mondo.json` is the canonical runtime ontology location.
- Missing `mondo.json` should raise a clear file/configuration error rather than
  silently returning no match.
- Fuzzy matching should auto-select the top candidate, but the stored context is
  required so fuzzy decisions can be audited later.
- No external ontology labels are loaded in this implementation; xrefs are
  identifier matches only.
- The matcher intentionally does not maintain a human-only MONDO allowlist or
  non-human blocklist until real paper failures justify one.
