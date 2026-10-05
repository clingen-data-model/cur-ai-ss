CORE_EXTRACTION_SPEC = """
---

The following rules define the evidence and extraction contract:

CORE EXTRACTION RULES:

- All extracted values wrapped with an EvidenceBlock MUST be supported by evidence,
  given as citations into the paper text you were shown.

HOW THE TEXT IS LABELLED:

- Every block of the paper carries an id printed in square brackets:
  - [paragraph-N] before a paragraph, list item or caption
  - [table-N] before a table's caption; the table's first column is named "anchor"
    and holds one id per data row, table-N-row-R
  - [figure-N] before a figure; its legend, if any, is the text that follows the id
- Ids of the supplement (everything at or after the "# Supplementary Material"
  heading) start with supp-: supp-paragraph-N, supp-table-N-row-R, supp-figure-N.
- Headings ("## Results") carry no id and are never evidence.

EvidenceBlock requirements:
  - value: the extracted value
  - reasoning: required explanation (see REASONING below)
  - citations: a list of {"anchor", "quote"} objects, one per block the value rests on

CITATIONS:

- Every EvidenceBlock whose value is a real answer (not null, not "Unknown", not
  false) MUST have at least one citation. A block with a concrete value and an
  empty citations list is invalid and will be rejected.
- anchor is an id copied EXACTLY as printed in the text. Never invent an id,
  renumber one, or count blocks to work one out. If you cannot see the id, you
  cannot cite the block.
- Cite every block the value rests on, not just the first: a value supported by a
  sentence, a table row and a pedigree gets three citations.
- quote is the shortest verbatim span of the cited block that supports the value:
  - a phrase or a sentence of a paragraph -- never the whole paragraph, the anchor
    already names it;
  - for a table, cite the row id (table-N-row-R) and put the text of the one cell
    that carries the value in quote; cite the table id (table-N) only for a fact
    about the table as a whole;
  - empty when the whole block is the evidence;
  - for a figure, empty when the image itself is the evidence (a pedigree); when a
    value comes from the figure's legend (the text after the id: "Fig. 3. ... (c)
    Case 17DG0679 ..."), quote the shortest span of that legend, as for a paragraph.
- quote MUST be copied verbatim from inside the cited block. Every citation is
  checked against the paper: an anchor that does not exist, or a quote that is not
  found inside its block, is rejected and you will be asked to correct it. Do NOT
  paraphrase, summarise, add words or place interpretive commentary in quote.
- If the value itself was constructed rather than copied (an identifier you
  assigned, a conclusion that follows from a rule), cite the block that supports
  the underlying fact rather than leaving citations empty.

REASONING:

- reasoning MAY include verbatim quotes from the input source text if helpful.
  - reasoning should primarily explain how the value was derived and why it was chosen.
  - reasoning is read by human curators reviewing extracted data — write it in plain language
    as if explaining your decision to a colleague. Do not use raw function or tool names
    (e.g. get_hpo_term, clinvar_lookup); describe what you looked up and what you found instead.
  - Any quoted text in reasoning must be copied exactly from the input source text.

PEDIGREE DESCRIPTION RULES:

- Some messages carry a "Pedigree Description" alongside the paper. It is a
  reading of a figure, written for you, and is NOT part of the paper's text. It
  names the figure it describes by its anchor (e.g. figure-2 or supp-figure-0).
- Never quote it. A quote is checked against the paper, so a sentence copied from
  the description points the curator at something the document does not contain.
- For a value taken from it, cite that figure anchor with an empty quote. The
  figure alone is sufficient evidence.
- Its wording may still inform reasoning, which is yours to write.

TABLE EVIDENCE RULES:

- A field is table-derived when the information is presented in a structured
  table (rows and columns) in the source. Cite the row: the id in that row's
  "anchor" column, with the cell text as the quote.
- A cell that carries only a flag ("+", "-", "Yes", "No", "Y", "N") or a value that
  repeats across the row ("de novo", "Severe", "Heterozygous") means nothing on its
  own: the same text sits under other columns, and the column header says which
  finding it answers. This is common when each column is a patient and a row is a
  feature, and equally when each row is a patient and each column is a feature
  (ventricular dilation, seizures, hearing: Yes, Yes, No ...). Then quote from the
  row's first cell (its label or id) through the cell that carries the value,
  copied exactly as printed with the "|" separators between cells, and stop at that
  cell: for the second patient's "+" in the row "Hypotonia | + | +", quote
  "Hypotonia | + | +"; for the first patient's, quote "Hypotonia | +"; for the
  seizures flag of "KCHYD154-1 | c.1823G>A | p.(Arg608His) | Yes | Shunt | Yes | Yes",
  quote through the cell in the seizures column. Do not include the leading row id
  column. Find the column by counting cells against the table's header row, and
  count to the right column and no further.
- Never quote a flag or repeated cell bare, and never quote only the row's label or
  id cell for a value that lives in another column: the label says whose row it is,
  not what the row says. The quote must end on the cell that carries the value.
- A vision-rebuilt table may carry <br> or <sup> markup inside cells; copy the
  cell as printed, the check tolerates markup and spacing differences.
- A table may be preceded by an "EXTRACTION WARNING" marker, meaning the automated
  extraction of that table failed and its rows are scrambled.
  - Values read from such a table are unreliable; prefer any other source in the paper.
  - Crucially, do NOT treat a value's absence from a flagged table as evidence that the
    paper does not report it. Say the value could not be read, rather than that it was
    not reported.
"""
