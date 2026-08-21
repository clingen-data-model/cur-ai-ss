CORE_EXTRACTION_SPEC = """
---

The following rules define the evidence and extraction contract:

CORE EXTRACTION RULES:

- All extracted values wrapped with an EvidenceBlock MUST be supported by evidence.
- Evidence must be:
  - Verbatim for text/table sources
  - Referenced via image_id for figures when applicable

- EvidenceBlock requirements:
  - value: extracted value
  - quote: verbatim quote when available
  - image_id: required for figure-derived evidence, using the image_id of the figure you
    were shown. Never invent one.
  - is_supplement: boolean flag indicating whether evidence came from a supplement
    - Set to true when evidence is extracted from supplementary material that may not be renderable in the PDF view
    - Set to false (or omit) when evidence is from the main paper
    - When true, coordinates may not be available for highlighting/linking in the UI
  - reasoning: required explanation

- At least one of quote or image_id MUST be provided.
  - Table-derived values are quoted like any other: give the row or cell text verbatim.
    A quote is highlighted on the page for the curator, which points at the value itself
    rather than at the table containing it.

CRITICAL:
- quote MUST contain ONLY verbatim text copied from the input source text.
  - No paraphrasing, summarization, or added words.
  - quote MUST contain enough context to be uniquely identifiable in the source. This typically means:
    - For table-derived values: include the full row or cell with row/column headers
    - For text: include surrounding context (e.g., section headers, case labels with full identifiers)
    - Avoid partial identifiers that are ambiguous (e.g., "Case 2" when "Case 2", "Case 23", "Case 24" exist; instead quote the full row or full context)
- A verbatim quote means an exact substring of the input source text with no modifications.
- reasoning MAY include verbatim quotes from the input source text if helpful.
  - reasoning should primarily explain how the value was derived and why it was chosen.
  - reasoning is read by human curators reviewing extracted data — write it in plain language
    as if explaining your decision to a colleague. Do not use raw function or tool names
    (e.g. get_hpo_term, clinvar_lookup); describe what you looked up and what you found instead.
  - Any quoted text in reasoning must be copied exactly from the input source text.
- Do NOT place interpretive commentary inside quote.
- Do NOT paraphrase text inside quote.

TABLE EVIDENCE RULES:

- A value taken from a table is quoted, not referenced by table number.
  - Quote the full row where possible: it is unique, and it carries the row label that
    identifies which patient or variant the value belongs to.
  - Where a row is too long, quote the cell together with enough of its row and column
    headers to be unambiguous.
  - Ambiguity is the thing to avoid: "Case 2" is a bad quote where "Case 2", "Case 23" and
    "Case 24" all exist. Quote the full row instead.

- Do NOT fabricate or approximate quote when the exact text is not available.

- Do NOT paraphrase table content into quote as a substitute for a verbatim quote.
- Do NOT put a table number in place of a quote. "Table 3" identifies a table, not a value.

- A table may be preceded by an "EXTRACTION WARNING" marker, meaning the automated
  extraction of that table failed and its rows are scrambled.
  - Values read from such a table are unreliable; prefer any other source in the paper.
  - Crucially, do NOT treat a value's absence from a flagged table as evidence that the
    paper does not report it. Say the value could not be read, rather than that it was
    not reported.
"""
