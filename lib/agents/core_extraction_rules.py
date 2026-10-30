# The flag rule is stated once, here, and reaches every agent: the paper-
# reading agents through CORE_EXTRACTION_SPEC, the lookup agents
# (harmonization, HPO and MONDO linking, compound het, computed segregation)
# by appending it to their own instructions. See lib/models/flag.py.
FLAG_RULES = """FLAGS -- decisions a curator should see:

- Prefer output a curator can review over nothing. When the paper suggests
  something but does not establish it, produce it in the uncertain form the
  output allows -- Unknown or Uncertain where a field has one, uncertain:
  true, a broader term, a Non-Proband -- and say so in its basis. A row a
  curator can delete costs one click; a row they must add by hand costs the
  identifier, the evidence and every downstream step.
  Leave something out only when the output has no uncertain form for it and
  including it would change a count curators score before review (an extra
  proband, members of a cohort the target gene does not cover), and flag
  that.
- Every value you return carries its basis. A flag is for what that
  basis cannot carry: a decision about something that is not in your
  output, or a call the paper itself leaves open. Raise one only when a
  curator who read the same text could reasonably decide differently AND the
  difference would change what is curated -- a row added or removed, a
  different term, variant, link or count. Most runs raise none or a few; a
  flag on every row means the bar is too low.
- Every flag is of one kind, and a decision that fits no kind is not a flag.
  The FLAGS section of your task says which of these it may raise:
  - excluded: something the paper describes that a rule here kept out of
    your output, where the paper gives a curator a reason to keep it -- a
    person, variant or finding in scope that a scope, identifier or evidence
    rule excluded, or a candidate left out to keep a count curators score.
    Say what the paper said and which rule applied. Not a group plainly
    outside the task.
  - conflict: two places in the paper disagree about one value, and you
    chose one.
  - ambiguous: two readings of the paper both fit, and you chose one.
  - inferred: a value taken from somewhere other than a statement about the
    thing itself -- a sentence about a group the paper does not place it in,
    a reference's title, a pedigree symbol, surrounding context. (A sentence
    about every member of a cohort or family the paper puts it in is a
    statement about it, where your task says so.)
  - unresolved: a lookup could not settle it -- no identifier, term or
    record was found, so the output is partial or null where a curator might
    find one.
  - mismatch: the best available term or record does not fit what the paper
    says -- a different organ, system, mechanism or consequence.
  - other_gene: a person linked to the target gene whom the paper also
    reports carrying a pathogenic or disease-causing finding in another gene
    that could account for their phenotype. Name the gene and the finding as
    the paper gives it.
- Flag only decisions your own output makes. A value you were given as input
  -- a patient's proband status, a family's membership, a variant's
  notation, a link's zygosity or a parent's carrier status -- was decided by
  the task that produced it, and its flag, if any, was raised there. Use it
  as given; do not flag it again.
- Never flag:
  - a field the paper does not state. Unknown, null or an empty list already
    says that, and "X not stated" is not a decision.
  - a value a rule here required: Unknown under a no-inference rule, a default
    the rules name, a choice a rule makes for you when the paper gives no
    basis. If the paper implies a value the rule withholds, put the implied
    value in that field's basis, not in a flag.
  - a result that is as good as the inputs allow: a broader ontology term when
    nothing closer exists, a transcript picked by the canonical rule when the
    paper named none, a preferred name that differs from the paper's wording.
  - your own process: a tool you did or did not call, a search that returned
    nothing, a step you skipped.
  - anything the basis on the value already says.
- Do not flag routine extraction: a value stated plainly and cited needs no
  flag. Raise one flag per decision, not per item it touches; a group left
  out for one reason is one flag that names its members.
- Each flag is an object with:
  - kind: one of the kinds above, from those your task allows.
  - about: the identifier of the extracted thing it concerns, copied exactly
    from your output or from the input you were given (a patient or family
    identifier, a variant as written, a phenotype concept), or null when it
    is about something not extracted.
  - flag: a block whose value is a short subject (who or what, in a few
    words), whose basis says what the paper says and what you did with
    it, and -- where the block has citations -- whose citations point at the
    block(s) the decision rests on.
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
  - [figure-N] before a figure; its legend, if any, is the text that follows the id,
    and a figure that could be read carries a quoted "Figure description" block
    right under the id (see FIGURE DESCRIPTION RULES)
- Ids of the supplement (everything at or after the "# Supplementary Material"
  heading) start with supp-: supp-paragraph-N, supp-table-N-row-R, supp-figure-N.
- Headings ("## Results") carry no id and are never evidence.

EvidenceBlock requirements:
  - value: the extracted value
  - basis: required explanation (see BASIS below)
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
  - for a figure, empty when the image as a whole is the evidence; when a value
    comes from the figure's legend (the text after the id: "Fig. 3. ... (c) Case
    17DG0679 ...") or from its "Figure description" block, quote the shortest span
    of that text, as for a paragraph.
- quote MUST be copied verbatim from inside the cited block. Every citation is
  checked against the paper: an anchor that does not exist, or a quote that is not
  found inside its block, is rejected and you will be asked to correct it. Do NOT
  paraphrase, summarise, add words or place interpretive commentary in quote.
- If the value itself was constructed rather than copied (an identifier you
  assigned, a conclusion that follows from a rule), cite the block that supports
  the underlying fact rather than leaving citations empty.

BASIS:

- basis MAY include verbatim quotes from the input source text if helpful.
  - basis should primarily explain how the value was derived and why it was chosen.
  - basis is read by human curators reviewing extracted data — write it in plain language
    as if explaining your decision to a colleague. Do not use raw function or tool names
    (e.g. get_hpo_term, clinvar_lookup); describe what you looked up and what you found instead.
  - Any quoted text in basis must be copied exactly from the input source text.

"""

_SPEC_TAIL = """
FIGURE DESCRIPTION RULES:

- A figure that could be read carries, right under its [figure-N] id, a quoted
  block headed "Figure description" that names what the figure shows (Pedigree,
  Chromatogram, Gel, Copy-number plot, Read pileup, Karyotype or FISH) and
  describes it: every individual a pedigree draws, with sex and affected status;
  for genotyping evidence, which labelled individual each trace, lane or panel
  belongs to, the variant shown and that individual's result.
- It is a vision model's reading of the image, not the paper's own words, and the
  curator sees the same block. Treat what it reports as what the figure shows:
  a symbol's sex and status, a trace's result, a lane's digest pattern are the
  paper stating those facts in its figure.
- For a value taken from it, cite the figure's anchor. The quote may be empty
  (the image as a whole) or the shortest span of the description that states
  the fact, copied verbatim; the check accepts either.
- Figures with no block were not read (a photograph, a schematic, a chart); the
  legend is all the text they have.

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
