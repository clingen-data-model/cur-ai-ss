# MONDO Disease Matching Strategy

This document describes the intended matching strategy for linking extracted
free-text disease names to MONDO ontology terms. It is a working guide for the
future implementation and should be revised as matching behavior is tested on
real papers.

## Source Data

Prefer `mondo.json` for implementation. It is OWLGraph JSON and is easier to
parse than `mondo.owl`.

Relevant structure:

- `graphs[0].nodes`: ontology nodes.
- `node.id`: full IRI, e.g. `http://purl.obolibrary.org/obo/MONDO_0013390`.
- `node.lbl`: primary MONDO label.
- `node.type`: use `CLASS` nodes.
- `node.meta.synonyms`: associated terms/synonyms.
- `node.meta.xrefs`: external database identifiers for the MONDO class.
- `node.meta.basicPropertyValues`: mappings and replacement metadata.
- `node.meta.deprecated`: marks obsolete terms.

Observed synonym predicates:

- `hasExactSynonym`
- `hasRelatedSynonym`
- `hasNarrowSynonym`
- `hasBroadSynonym`

Observed synonym types include abbreviations, deprecated synonyms, ambiguous
synonyms, dubious synonyms, misspellings, and non-human synonyms. These should
not all be treated equally, but the matcher should not try to infer whether a
MONDO class itself is human-only.

## Deterministic Matching Tiers

Run deterministic matching before fuzzy matching. These matches should use
normalized exact comparison, not token-based similarity.

Recommended normalization:

- Unicode normalize.
- `casefold()`.
- Trim leading/trailing whitespace.
- Collapse repeated whitespace.
- Normalize hyphen, en dash, and em dash to a single hyphen.
- Strip surrounding quotes.

Avoid aggressive normalization in the deterministic pass. Do not remove numbers,
gene symbols, or subtype tokens, because they often distinguish disease terms.

### Tier 1: Direct MONDO ID

If the extracted text contains a MONDO CURIE or MONDO IRI, resolve it directly.

Examples:

- `MONDO:0013390`
- `http://purl.obolibrary.org/obo/MONDO_0013390`

Validate that the term exists and is not deprecated. If it is deprecated, apply
the deprecated-term handling rules below.

### Tier 2: Exact Primary Label

Match normalized extracted text to normalized `node.lbl`.

This is the highest-confidence text match. It should outrank all synonym and
associated-term matches.

Example:

- Extracted: `Stargardt disease`
- MONDO label: `Stargardt disease`
- Result: `MONDO:0019353`

### Tier 3: Exact Synonym Or Associated Term

Match normalized extracted text to normalized `meta.synonyms[*].val`.

Treat matches differently by predicate:

- `hasExactSynonym`: strong deterministic match.
- `hasRelatedSynonym`: deterministic candidate, lower confidence.
- `hasNarrowSynonym`: deterministic candidate; direction matters.
- `hasBroadSynonym`: deterministic candidate; direction matters.

Example:

- Extracted: `limb-girdle muscular dystrophy type 2Q`
- MONDO label: `autosomal recessive limb-girdle muscular dystrophy type 2Q`
- MONDO synonym: `hasRelatedSynonym = limb-girdle muscular dystrophy type 2Q`
- Result candidate: `MONDO:0013390`

### Tier 4: External Identifier / Xref

If extracted text contains an external disease identifier, match against
`meta.xrefs` and exact mapping properties in `meta.basicPropertyValues`.

Examples:

- `OMIM:613723`
- `Orphanet:254361`
- `DOID:0110285`
- `NCIT:C84692`

Node-level `meta.xrefs` are identifier mappings for the MONDO class as a whole.
They are not text labels and they are not additional disease names. For example,
if `GARD:0016535` appears in `MONDO:0007947`'s `node.meta.xrefs`, then extracted
text containing the identifier `GARD:0016535` can be treated as an exact
external-ID match to `MONDO:0007947`. That does not mean the GARD record's text
label is available for exact or fuzzy matching from `mondo.json` alone.

Synonym-level `xrefs` have a different meaning: they are provenance for that
specific synonym string. They should not be promoted to separate match strings.

External identifier matches are strong when they map uniquely to one
non-deprecated MONDO term, especially when the MONDO metadata marks the
relationship as an exact match. They should rank below direct MONDO IDs and
exact MONDO label/synonym text matches, because they are cross-ontology
identifier mappings rather than MONDO-native text matches.

### Tier 5: Unique Abbreviation

MONDO includes abbreviation synonyms such as `LGMD2Q`, `EBS`, and `RP1`.

Only auto-resolve abbreviation matches when the normalized abbreviation maps to
exactly one non-deprecated MONDO term. If an abbreviation maps to multiple
terms, return candidates rather than choosing silently.

### Tier 6: Deprecated Term Replacement

Do not return deprecated terms as final matches by default.

If a deterministic match lands on `meta.deprecated = true`, inspect replacement
metadata:

- `IAO_0100001` in `basicPropertyValues`: preferred replacement term.
- `oboInOwl:consider`: weaker replacement candidate.

Recommended behavior:

- If there is one valid replacement, return the replacement and record that the
  extracted text matched a deprecated term.
- If there are multiple replacements or no replacement, return candidates or no
  match for later review.

## Tie Breaking

Exact matching can produce multiple MONDO candidates. For example, a broad
disease name may be the primary label of one term and a related synonym of a
more specific subtype.

Recommended precedence:

1. Direct MONDO ID.
2. Exact primary label.
3. `hasExactSynonym`.
4. External exact identifier match.
5. `hasRelatedSynonym`.
6. `hasNarrowSynonym` or `hasBroadSynonym`.
7. Unique abbreviation.
8. Deprecated term replacement.

If multiple terms tie in the same tier, do not silently choose. Return candidate
matches for later fuzzy, agent, or human adjudication.

## Fuzzy Matching Boundary

Fuzzy matching should run only after deterministic matching fails or produces
ambiguous candidates.

The current HPO strategy uses RapidFuzz `token_sort_ratio` over all term names
and synonyms, deduplicates by ontology ID, and returns top candidates for agent
selection. MONDO should start more conservatively because disease names often
depend on subtype numbers, inheritance modifiers, gene names, and abbreviation
context.

Open questions for the fuzzy phase:

- Which synonym predicates should participate in fuzzy matching?
- Should broad/narrow synonyms be excluded from fuzzy matching or only ranked
  lower?
- What score cutoffs are acceptable for disease terms?
- Should fuzzy results be auto-selected, or always passed to an agent/reviewer?
- Should disease context such as gene symbol or inheritance mode affect ranking?

## Recommended Initial Implementation Shape

Build a MONDO lookup module that:

- Loads and caches `mondo.json`.
- Filters to non-deprecated MONDO `CLASS` nodes for normal matching.
- Does not attempt to identify or exclude non-human/cross-species MONDO classes.
  Rare non-human false matches are an accepted v1 risk because match context and
  manual edits can correct them.
- Builds separate normalized indexes for labels, synonyms by predicate,
  abbreviations, and external identifiers.
- Uses `node.lbl` and `meta.synonyms[*].val` for text matching.
- Uses `node.meta.xrefs` and mapping IDs in `meta.basicPropertyValues` only for
  identifier matching, not as text labels.
- Returns a structured match result containing:
  - `mondo_id`
  - `term`
  - `match_type`
  - `matched_text`
  - optional candidate list when ambiguous
- Leaves fuzzy matching as a second-stage candidate generator until thresholds
  are validated.
