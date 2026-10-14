# The flag rule is stated once, here, and reaches every agent: the paper-
# reading agents through CORE_EXTRACTION_SPEC, the lookup agents
# (harmonization, HPO and MONDO linking, compound het, computed segregation)
# by appending it to their own instructions. See lib/models/flag.py.
FLAG_RULES = """FLAGS -- decisions a curator should see:

- Every value you return carries its reasoning. A flag is for what that
  reasoning cannot carry: a decision about something that is not in your
  output, or a call the paper itself leaves open. Raise one in the "flags"
  list of your output when:
  - something a curator might have expected was left out under a rule rather
    than for being nothing at all -- a person, variant or finding the paper
    mentions that a scope, identifier or evidence rule excluded. Say which
    rule applied and what the paper said, so a curator who reads the rule
    differently can add it.
  - a value rests on a judgment the paper does not settle: two sources
    disagree, a status is implied rather than stated, a choice was made
    between readings, a rule here changed something's standing in a way a
    curator may not expect.
- Do not flag routine extraction: a value stated plainly and cited needs no
  flag. Raise one flag per decision, not per item it touches; a group left
  out for one reason is one flag that names its members.
- Each flag is an object with:
  - about: the identifier of the extracted thing it concerns, copied exactly
    from your output or from the input you were given (a patient or family
    identifier, a variant as written, a phenotype concept), or null when it
    is about something not extracted -- the usual case.
  - flag: a block whose value is a short subject (who or what, in a few
    words), whose reasoning says what you decided, under which rule, and what
    a curator might decide instead, and -- where the block has citations --
    whose citations point at the block(s) the decision rests on.
- "flags" is empty when there was nothing to flag.
"""

_SPEC_HEAD = """
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
    about the table as a whole or for a header cell (see TABLE EVIDENCE RULES);
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

"""

_SPEC_TAIL = """
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
- The header row has no id of its own, and no data row contains its text. When the
  value is a header cell -- above all a patient's label in a table with one patient
  per column ("Pat. 1 *", "Pat. 2 *") -- cite the table id (table-N) and quote that
  one header cell alone, copied exactly as printed, footnote markers such as * or
  a dagger included. Never cite a data row for text that appears only in the
  header: the row does not contain it and the citation is rejected. Never quote a
  cell from that patient's column in the label's place: a genotype or feature cell
  says what the patient has, not who the patient is.
- A vision-rebuilt table may carry <br> or <sup> markup inside cells; copy the
  cell as printed, the check tolerates markup and spacing differences.
- A table may be preceded by an "EXTRACTION WARNING" marker, meaning the automated
  extraction of that table failed and its rows are scrambled.
  - Values read from such a table are unreliable; prefer any other source in the paper.
  - Crucially, do NOT treat a value's absence from a flagged table as evidence that the
    paper does not report it. Say the value could not be read, rather than that it was
    not reported.
"""

CORE_EXTRACTION_SPEC = _SPEC_HEAD + FLAG_RULES + _SPEC_TAIL
