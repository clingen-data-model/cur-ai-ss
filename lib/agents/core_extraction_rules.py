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
  - table_id: required when evidence is derived from a table (see TABLE EVIDENCE RULES)
    - A field is considered table-derived if the information is explicitly presented in a structured table (rows and columns) in the source.
    - If a verbatim quote cannot be extracted (i.e., the exact table row or cell text is not available as a substring of the input text), then table_id alone is sufficient.
  - image_id: required for figure-derived evidence
  - reasoning: required explanation

- At least one of:
  quote, table_id, or image_id MUST be provided.

CRITICAL:
- quote MUST contain ONLY verbatim text copied from the input source text.
  - No paraphrasing, summarization, or added words.
  - If possible, the quote should uniquely identify a location in the text.  Give enough detail such that this is possible.
- A verbatim quote means an exact substring of the input source text with no modifications.
- reasoning MAY include verbatim quotes from the input source text if helpful.
  - reasoning should primarily explain how the value was derived.
  - Any quoted text in reasoning must be copied exactly from the input source text.
- Do NOT place interpretive commentary inside quote.
- Do NOT paraphrase text inside quote.

TABLE EVIDENCE RULES:

- When a field is derived from a table:
  - table_id MUST be provided.
  - table_id is a 0-based index representing the sequential position of tables in the document as they are processed by the extraction system (not the table number shown in the markdown).
    - Example: If the markdown shows "Table 1", "Table 3", "Table 5", these correspond to table_id 0, 1, 2 respectively.
    - Count only tables that appear in the markdown, in order from first to last.

  - quote MUST contain a verbatim quote from the table WHEN POSSIBLE.
    - This should be either:
      - the full row containing the relevant value, OR
      - the minimal exact cell text copied exactly as shown

  - If a verbatim quote cannot be extracted (i.e., the exact table row or cell text is not available as a substring of the input text), then:
    - table_id alone is sufficient.
    - quote SHOULD be omitted.
    - reasoning MUST explain how the value was determined from the table.

- Do NOT fabricate or approximate quote when the exact text is not available.

- Do NOT paraphrase table content into quote as a substitute for a verbatim quote.
- Do NOT use markdown table numbers (e.g., "Table 3") as table_id; always use 0-based sequential indexing.
"""
