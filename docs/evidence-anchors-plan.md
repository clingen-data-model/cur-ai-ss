> **Status: chunk 1 (anchored documents on disk, side by side) in progress on branch `evidence-anchors`; the rest is not implemented** (written 2026-09-29, ids renamed to the self-describing grammar the same day). Design for replacing quote re-finding with structural evidence anchors. Line numbers refer to the tree at commit `226d109d` and will drift.

# Evidence anchors: cite document structure instead of re-finding quotes

## Context

Every extracted field carries an `EvidenceBlock` (`quote`, `table_id`, `image_id`,
`is_supplement`). Both viewers then try to *re-find* that evidence at render time: the
PDF tab aligns the quote against `words.json` (Smith-Waterman), the Markdown tab runs a
regex over `raw.md`. Three problems fall out of that design, and we have been patching
them one matcher at a time:

- **Table quotes.** Agents are told to copy a pipe-table row verbatim; 28% of those
  (2,177 of 7,659 in prod) don't match `raw.md` exactly (vision-rebuilt tables, `<br>`/
  `<sup>` stripping, spacing), so highlighting falls back to heuristics or nothing.
- **Inexact matches.** Justified-text double spacing, hyphenation, ligatures -- every
  fuzzy matcher we've tried has a failure mode that lands a wrong or truncated highlight.
- **Evidence strewn through a paper.** A block can cite one quote, one table, one
  figure; a value supported by a sentence *and* a table row *and* a pedigree can't say so.

Worse, the ids agents cite today are unreliable *before* any matching happens:
`table_id` is "count the pipe tables in the text you were given" (drifts when
`relevant_sections_md` drops sections, when supplement tables are appended, and because
`parse.py` skips tables without an image), and nothing in the text labels `image_id` at
all.

**Decision:** agents cite explicit structural anchors that we print into the markdown
they read; the UI highlights by anchor, never by matching. We can re-run every paper,
so no backfill or compatibility shim is needed.

## Design

### Anchor ids

Printed into the agent's markdown and copied back verbatim. Grammar
(`^(supp-)?(paragraph-\d+|table-\d+(-row-\d+)?|figure-\d+)$` -- self-describing and
hyphen-only, a couple of tokens more than `p54`/`t1.r7` and far harder to mangle):

| id | meaning | resolves to |
|---|---|---|
| `paragraph-12` | Docling text item `#/texts/12` (paragraph, list item, caption) | its `prov` boxes |
| `table-1` | table `#/tables/1` | table `prov` box |
| `table-1-row-3` | data row 3 (0-based, header excluded) of that table's *rendered* markdown | row box from `grid` cell boxes when they line up, else the table box |
| `figure-0` | picture `#/pictures/0` | picture `prov` box |
| `supp-...` | same, in the supplement document | markdown tab only (no supplement PDF) |

Section headers get no id (they're never evidence). Ids are Docling indices, so every
artifact keyed by "table N"/"image N" (`tables/N.*`, `images/N.*`, pedigree `image_id`)
switches to the Docling index too -- this also fixes the existing drift bug where
`parse.py`'s counters skip items without an image.

### `anchored.md` + `anchors.json` -- the two artifacts everything derives from

**Implemented in chunk 1** (`lib/misc/pdf/anchors.py`, written by `parse_content` and by
`lib/bin/backfill_documents.py` into `{CAA_ROOT}/documents/{id}/{main|supplement}/`,
side by side with `extracted_pdfs/`). Built from the `DoclingDocument` with
`MarkdownDocSerializer(doc, params=MarkdownParams(escape_html=False,
escape_underscores=False)).get_parts()` -- one part per body item, in reading order;
a captioned table/figure part spans its caption too; a list part spans its items.

`anchored.md` is the **only** text: what agents read and what curators will see, with
the ids printed in (see "What agents read" below). `anchors.json` is a pure id ->
geometry index, nothing stored twice:

```python
class PageBox(BaseModel):      # PDF points, TOP-LEFT origin -- what PdfViewer draws
    page_no: int; x: float; y: float; width: float; height: float

class Anchor(BaseModel):
    id: str                               # paragraph-12 | table-1 | figure-0, 'supp-' prefixed in a supplement
    boxes: list[PageBox] = []             # from prov (BOTTOMLEFT -> top-left via doc.pages[n].size.height); [] for DOCX/XLSX
    row_boxes: list[list[PageBox]] = []   # tables: one entry per rendered data row (so the row ids are known from
                                          # this file alone); row r <-> grid row r+1, from grid cell bboxes (TOPLEFT);
                                          # [] for a row when vision-corrected or the grid doesn't line up with the
                                          # rendered rows => resolve to the table box
```

Everything else is derivable and therefore not stored: the kind is the id prefix; a
figure's PNG is `document_image_path(paper_id, N, supplement)`; "vision-corrected" is
the existence of `tables/N.vision.md`; the unrecovered-table verdict is the existence of
`tables/N.unrecovered`, read once, at build time, and printed as the
`UNRECOVERED_TABLE_MARKER` line above the table. Headers are printed untagged and have
no anchor entry. Table text = `serialize_captions(item)` + `tables/N.vision.md` when
present, else Docling's own pipe table. XLSX supplements (no Docling doc) go through
`anchored_from_markdown()`: blank-line paragraphs, runs of `|` lines as tables,
`![...]()` lines as figures, sequential ids, no boxes.

### What agents read

`fulltext_md` / `relevant_sections_md` keep their names and signatures (all handler
call sites unchanged) but read `anchored.md`, which looks like:

```
## Results                                   <- headers untagged

[paragraph-54] Two missense variants (c.3442G>A ...) of ZFPM2 were identified in patient B430 and B546 (Table 2).

[table-1] Table 2 Information regarding the rare variants identified in the TOF patients
| anchor | ClinVar | Likely pathogenic | ... |
|--------|---------|-------------------|-----|
| table-1-row-0 | Internal database | 2 | ... |
| table-1-row-7 | Patient ID | B151 | ... |

[figure-2] Figure: Fig. 3 Rare variants of JAG1 identified in patients. ...
```

The row-id column is added by a line-level transform of the pipe table (works for
Docling and vision tables alike); the viewer derives the same `table-1-row-3` by counting
rendered `<tr>`s, so both sides agree by construction. The EXTRACTION WARNING marker
carries over. The supplement is introduced by the literal `SUPPLEMENTARY_MATERIAL_HEADER`
(`# Supplementary Material (XLSX)`) exactly as today -- `core_extraction_rules.py:23-24`
tells agents to look for that heading, so block rendering must emit it verbatim (test
it). `relevant_sections_md`'s section skipping is re-implemented over `anchored.md`: match the
classifier's header strings against `#` headings (strip `#`, lowercase -- same rule as
today), skip until the next heading *of any kind* -- an unmatched heading ends the skip,
never inherits it (commit `b4843564`: inheriting it let References swallow every table
printed after it in paper 97; test this case explicitly). Headers
are untagged, so the classifier's header extraction (`handlers.py:367-415`, which reads
`fulltext_md`) is unaffected by the `[paragraph-N]` prefixes on paragraphs.

### Schema

```python
class EvidenceBlock(ReasoningBlock[T]):
    anchors: list[str] = []      # every location the value rests on
    quote: str | None = None     # optional verbatim excerpt of a cited paragraph/row, for curators
```

`table_id`, `image_id`, `is_supplement` are removed (the `supp-` prefix carries supplement-
ness). Validation is deliberately lenient about *form* and strict about *presence*,
matching today's contract: a `field_validator` drops anchors that don't match the
grammar (logged), and `validate_sources` raises when `require_source`, the value is real,
and no anchor survives -- exactly when today's "at least one of quote/table_id/image_id"
raises. Manual-output agents (`run_with_manual_output`) get a repair retry from that;
native-schema agents (`Runner.run(output_type=...)`: segregation, pedigree, phenotype
linking, paper metadata) fail the task, as they do today. Union-node cost drops from 3
nullable fields to 1 (`docs/anthropic-migration.md` census: the native-schema agents at 7
nodes get cheaper, not costlier).

After each producing agent runs, `prune_unknown_anchors(output, known_ids)` drops any
anchor that isn't a block id in that paper's `anchors.json` (+ `anchored.md`) (with a warning) -- a mis-
copied id degrades to "no highlight", never a wrong box.

### Highlighting

- `POST /papers/{id}/grobid-annotation` takes `{anchors, quote, color}` and maps each
  anchor to boxes via `anchors.json` (+ `anchored.md`) (`paragraph` → `boxes` narrowed by the quote when it aligns,
  `table` → table box, `table-N-row-R` → `row_boxes[r]` or the table box, `figure` → box; `supp-` anchors
  contribute nothing). Returns `[]` rather than 404 when nothing resolves.
- `GET /papers/{id}/document` replaces `/markdown-annotation`: `{main: string,
  supplement: string | null}` -- the `anchored.md` texts, which the viewer renders,
  turning `[anchor-id]` tags and the `anchor` column into `data-anchor` attributes.
- The markdown tab renders `anchored.md` (tables with a `tr`
  component that stamps `data-anchor="table-1-row-{i}"`; pictures as `<figure>`), sets
  `data-evidence-highlight` on every element whose anchor is in the evidence's set, and
  scrolls to the first. One attribute, styled per element (`span`/`text`/`tr` →
  background, `table`/`img` → ring). No `<mark>`; the only splice is the in-block
  narrowing span below, which by construction can never straddle a table cell.
- **Quote narrowing** -- sentence-level precision. Docling has no sentence structure, so
  a `p` anchor alone is paragraph-level; the quote (verbatim, from the cited paragraph)
  narrows it. Unlike today, the quote is only ever matched *inside the cited block*, and
  a miss falls back to the block -- it can narrow a correct highlight, never produce a
  wrong one. PDF: `find_best_match(quote, words_within(block.boxes, words.json))`, then
  `words_to_grobid_annotations` as today; else the block's boxes. Markdown: whitespace-
  tolerant exact match inside `block.markdown`, splice a `<span data-evidence-highlight>`
  (rehype-raw + rehype-sanitize allowing `dataEvidenceHighlight` on `span`, the default
  schema's `span` tag is already allowed); else the whole block. Table rows and figures
  never narrow. Main paper only on the PDF side (supplements have no PDF tab).

## Backend changes

**`lib/misc/pdf/anchors.py` (landed in chunk 1)** -- `Anchor`/`PageBox`; `build_anchored(doc, paper_id=,
supplement=) -> (md, anchors)` from `get_parts()`; `anchored_from_markdown(md)` for XLSX;
`write_anchored`/`load_anchors`; `boxes_for_anchor(anchor, anchors)`;
`parse_anchor(id) -> (supplement, kind, index, row)`; `ANCHOR_RE`.

**`lib/misc/pdf/parse.py`** -- key `tables/N.*` and `images/N.png` by Docling index
(`doc.tables.index(item)` / `doc.pictures.index(item)`), write `.md` for every table
even without an image (skip only the PNG); write `anchors.json` (+ `anchored.md`) after `correct_tables`;
XLSX path writes the anchored files too. Delete `split_by_sections`, the `sections/` dir and
`images/N.md` captions (captions are the `[figure-N]` lines of `anchored.md`; the pedigree handler reads
them from there).

**`lib/misc/pdf/paths.py`** -- the `document_*` helpers landed in chunk 1; reimplement `fulltext_md` and
`relevant_sections_md` on `anchored.md`; delete `raw_md`, `apply_table_corrections`,
`_flag_unrecovered_tables` (the marker is printed into `anchored.md` at build time), `sections_md`, `tables_md`,
`pdf_section_markdown_path`, `pdf_image_caption_path` (confirm unused with grep first).
`save_as_markdown` (raw.md) stays as a debugging artifact only.

**`lib/models/evidence_block.py`** -- schema above; anchor validator; update the
schema-limit comment. **`lib/models/base.py`** `manual_evidence_block` → `anchors=[]`.
**`lib/models/paper.py`** -- `HighlightRequest{anchors, color}`; delete
`MarkdownAnnotationRequest`; `lib/models/__init__.py` re-exports.

**`lib/misc/pdf/highlight.py`** -- `anchors_to_grobid_annotations(paper_id, anchors,
quote, color)` reads the precomputed boxes from `anchors.json` (+ `anchored.md`) (never the 28 MB
`raw.json`, which `figures_to_grobid_annotations` re-parses on every call today); for
`p` anchors with a quote, `words_within(boxes, words)` filters `words.json` to the
block's page(s)/boxes (word centre inside a box, small tolerance) and the existing
`find_best_match` + `words_to_grobid_annotations` run on that subset, falling back to
the block boxes. Delete `figures_to_grobid_annotations` and `MarkdownAnnotationResp`;
keep `parse_words_json`/`words.json`, `merge_adjacent_polygons`, `PairwiseAligner`.

**`lib/agents/table_correction_agent.py:126`** -- docstring cites
`apply_table_corrections`; say corrections are applied when `anchors.json` (+ `anchored.md`) is built.

**`lib/api/app.py`** -- `grobid_annotation` rewritten on anchors; `/markdown-annotation`
→ `GET /document`; `_from_storage` unchanged (extra keys in old JSON are ignored).

**`lib/tasks/handlers.py`** -- call `prune_unknown_anchors` after each of the 7
producing agents (variants L468, pedigree L527, patients L605, demographics L700,
segregation L805, occurrences L1239, phenotypes L1487, paper metadata L417). The
pedigree figure listing (L543-560) currently probes `images/0.png, 1.png, ...` and stops
at the first gap -- with Docling-indexed files that would truncate the list, so it
iterates `figure-N` anchors instead (caption from `anchored.md`, PNG by path) and prints
`anchor: figure-<N>` / `supp-figure-<N>` rather than `image_id`/`is_supplement`. `analyze_pedigree_image`
keeps its `(image_id, is_supplement)` signature; `PedigreeDB.image_id` (and
`PedigreeResp.image_url` via `pdf_image_path`) simply becomes the Docling picture index
-- no migration, the re-run rewrites every pedigree row. `identifier_quote`, passed to
the demographics/occurrence/phenotype agents (L736, L1284, L1521), becomes
`quote or describe_anchors(anchors)` (e.g. "Table 2 row 7"), and the two prompts that
describe it (`patient_variant_occurrence_agent.py:24`,
`patient_phenotype_linking_agent.py:24`) say so.

**Prompts** -- rewrite the evidence contract in `lib/agents/core_extraction_rules.py`
(anchors grammar; copy ids exactly as printed; cite *every* location the value rests on;
quote is an optional verbatim excerpt of a cited block; `supp-` = supplement; pedigree →
`f<N>`; EXTRACTION WARNING rule kept; delete the "count the tables" rules) and the
per-agent restatements: `patient_extraction_agent.py:36-42,110-112,158-162`,
`patient_demographics_agent.py:24-30,83-85`, `segregation_evidence_extractor.py:41-45`,
`patient_phenotype_linking_agent.py:39-41,125,329,383`,
`variant_extraction_agent.py:17,153,216`, `manual_output.py:36-51`,
`lib/agents/AGENT_GUIDE.md`.

**Re-run tooling** -- `lib/bin/requeue_all_papers.py`: for every paper, the same path as
`POST /papers/{id}/tasks {type: PDF_PARSING}` (snapshot first, then
`invalidate_descendants` + `enqueue_all_instances`), so the pre-redesign state is kept
in a snapshot per paper.

## Frontend changes (`frontend/src`)

- Regenerate the API client (`pnpm api:generate` after `./bin/generate-api-spec`).
- `components/EvidencePopover.tsx` -- `EvidenceLike.anchors?: string[]` (optional:
  `OccurrenceEditableCells.tsx:244-252` synthesises note-only blocks, and `hpo` blocks in
  `PhenotypesTable.tsx:150` are `ReasoningBlock`s); `canViewEvidence = (anchors?.length
  ?? 0) > 0`; show `quote` when present plus one chip per anchor via a
  `describeAnchor(id)` helper ("Paragraph", "Table 2 · row 3", "Figure 1",
  "Supplement · …"); button label "View in PDF" when any main-document anchor exists,
  else "View in Markdown".
- `components/PdfHighlightProvider.tsx` -- `HighlightTarget = {anchors, quote}`; posts
  `{anchors, quote, color}`; opens the PDF tab if any non-`supp-` anchor, else markdown;
  passes `anchors` and `quote` to the document viewer.
- `components/MarkdownEvidenceViewer.tsx` → replaced by
  `components/DocumentEvidenceViewer.tsx` as described under Highlighting; query key
  `['document', paperId]`; main and supplement texts rendered in one scroll with the
  same `# Supplementary Material` divider.
- `components/PdfViewer.tsx` -- unchanged.
- `lib/routeTree.ts`, `TaskDAG.tsx`, `PaperActions.tsx` -- unchanged (no new task type).

## Tests

- `test/evagg/pdf/test_anchors.py` (landed in chunk 1): ids, boxes, row boxes, vision/
  unrecovered tables, supplement prefix, XLSX markdown, anchor grammar, resolution.
- `test/evagg/pdf/test_parse.py`: assert `anchors.json` (+ `anchored.md`) exists and `tables/`/`images/`
  file ids match block ids. Its ~10 tests at L127-350 build `raw.md` fixtures and assert
  on `fulltext_md`/`apply_table_corrections`/the warning marker -- rewrite them against
  `anchors.json` (+ `anchored.md`) fixtures (an `Anchor` list plus an `anchored.md` with one table carrying
  `warning`, with and without a `.vision.md`).
- `test/evagg/pdf/test_highlight.py`: keep the `find_best_match` test; add anchor →
  annotation resolution for each anchor form, `words_within` box filtering, and the
  narrow-or-fall-back behaviour (quote aligns inside the block → word boxes; quote
  absent or doesn't align → block boxes).
- `test/api/test_markdown_annotation.py` → `test_document.py` (main, supplement, 404).
- `test/models/test_evidence_markup.py` + new cases: anchor grammar accepted/rejected,
  `require_source` needs an anchor, `prune_unknown_anchors`.
- Update fixtures that build blocks with `table_id=`/`image_id=`: `test/models/
  test_converters.py:77-183` (incl. L134, L180-182), `test/models/test_evidence_markup.py:
  91-101`, `test/api/test_app.py` (inline evidence dicts ~L249-865),
  `test/api/test_snapshots.py:94` (L188 is `PedigreeDB.image_id`, untouched),
  `test/migrations/test_alembic.py:40-90` (raw JSON fixtures -- leave as historical
  data, they only exercise the edits backfill).

## Verification

1. `uv run ruff check lib && uv run ruff format --check lib test && uv run mypy lib`;
   `ENV_FILE=.env.test uv run pytest test/`.
2. Frontend: `pnpm type-check && pnpm lint && pnpm build`.
3. Locally, run `PDF_PARSING` on the MASP1 test paper (PMID 26419238, the paper used to
   validate the Claude switch) and inspect `anchors.json` (+ `anchored.md`) and `fulltext_md` output by eye:
   ids on every paragraph, id column on every table, warning marker on a corrupted table.
4. Run the full pipeline on it and check the evidence JSON: `anchors` populated, no
   `table_id`/`image_id`, `prune_unknown_anchors` warnings (if any) in the worker log.
5. In the SPA: paper 13 / patient B546 identifier evidence → PDF tab boxes the quoted
   sentence (not the whole paragraph) on page 5 plus Table 2; markdown tab highlights the
   sentence inside `p54` and the table, both at once; paper 27's justified-text quote →
   sentence highlighted with correct boundaries; a pedigree (paper 20) → figure ring; a
   supplement anchor → markdown tab only; a quote that doesn't align → whole paragraph.
6. Deploy, then `requeue_all_papers.py` on dev-caa; spot-check three papers from the
   earlier QA set (19, 27, 83) once their pipelines finish.

## Out of scope

- Streamlit UI (retiring) -- its evidence display will stop showing table/figure links.
- Column anchors for transposed tables (`table-1-col-11`) -- rows only for now; cite the whole
  table when a column is the real unit.
- Prev/next navigation between multiple highlighted anchors.
