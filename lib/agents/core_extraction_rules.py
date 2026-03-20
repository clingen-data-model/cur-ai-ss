CORE_EXTRACTION_SPEC = """
---

The following rules define the evidence and extraction contract:

CORE EXTRACTION RULES:

- All extracted values MUST be supported by evidence.
- Evidence must be:
  - Verbatim for text/table sources
  - Referenced via image_id for figures when applicable

- EvidenceBlock requirements:
  - value: extracted value
  - evidence_context: verbatim quote when available
  - table_id: required when evidence is derived from a table (see TABLE EVIDENCE RULES)
    - A field is considered table-derived if the information is explicitly presented in a structured table (rows and columns) in the source.
    - If a verbatim quote cannot be extracted (i.e., the exact table row or cell text is not available as a substring of the input text), then table_id alone is sufficient.
  - image_id: required for figure-derived evidence
  - reasoning: required explanation

- At least one of:
  evidence_context, table_id, or image_id MUST be provided.

CRITICAL:
- evidence_context MUST contain ONLY verbatim text copied from the input source text.
  - No paraphrasing, summarization, or added words.
- A verbatim quote means an exact substring of the input source text with no modifications.

- reasoning MAY include verbatim quotes from the input source text if helpful.
  - reasoning should primarily explain how the value was derived.
  - Any quoted text in reasoning must be copied exactly from the input source text.

- Do NOT place interpretive commentary inside evidence_context.
- Do NOT paraphrase text inside evidence_context.

TABLE EVIDENCE RULES:

- When a field is derived from a table:
  - table_id MUST be provided.

  - evidence_context MUST contain a verbatim quote from the table WHEN POSSIBLE.
    - This should be either:
      - the full row containing the relevant value, OR
      - the minimal exact cell text copied exactly as shown

  - If a verbatim quote cannot be extracted (i.e., the exact table row or cell text is not available as a substring of the input text), then:
    - table_id alone is sufficient.
    - evidence_context SHOULD be omitted.
    - reasoning MUST explain how the value was determined from the table.

- Do NOT fabricate or approximate evidence_context when the exact text is not available.

- Do NOT paraphrase table content into evidence_context as a substitute for a verbatim quote.
"""
