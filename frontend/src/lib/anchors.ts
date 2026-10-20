/* Evidence anchor ids, as the backend prints them into the paper's anchored
 * markdown and the agents copy them back (lib/misc/pdf/anchor_ids.py is the
 * source of truth for the grammar; keep ANCHOR_RE identical to its):
 *
 *   paragraph-12        a paragraph, list item or caption
 *   table-1             a table;  table-1-row-7  its data row 7 (0-based, header excluded)
 *   figure-0            a figure
 *   supp-...            the same, in the paper's supplement (which has no PDF view)
 *
 * The numbers are Docling item indices -- the same ones that key the
 * tables/N.* and images/N.png files -- not the paper's own "Table 2"
 * numbering, so a chip built from describeAnchor() says "Table 2 · row 8"
 * where the paper's caption may say "Table 3". That is why the chip also
 * carries the PDF page (GET /papers/{id}/anchor-pages): "Table 8 · row 4 ·
 * p. 13" is findable, "Table 8" alone is not.
 *
 * Only the display counts from one: describeAnchor() adds 1 to the index and
 * row so a curator never meets "Image 0" or "row 0". The ids keep their
 * 0-based numbers, which is what the API, the files and the agents use.
 */
export type AnchorKind = 'paragraph' | 'table' | 'figure'

export interface ParsedAnchor {
  supplement: boolean
  kind: AnchorKind
  index: number
  row: number | null
}

const SUPPLEMENT_PREFIX = 'supp-'
const ANCHOR_RE = /^(supp-)?(paragraph|table|figure)-(\d+)(?:-row-(\d+))?$/

export function parseAnchor(id: string): ParsedAnchor | null {
  const match = ANCHOR_RE.exec(id)
  if (!match) return null
  const kind = match[2] as AnchorKind
  const row = match[4] === undefined ? null : Number(match[4])
  if (row !== null && kind !== 'table') return null // -row- only makes sense on a table
  return { supplement: match[1] !== undefined, kind, index: Number(match[3]), row }
}

export function isSupplementAnchor(id: string): boolean {
  return id.startsWith(SUPPLEMENT_PREFIX)
}

/** 'supp-table-1-row-7' -> 'supp-table-1' (a table id is returned unchanged). */
export function tableOfRow(id: string): string {
  return id.replace(/-row-\d+$/, '')
}

const KIND_LABEL: Record<AnchorKind, string> = {
  paragraph: 'Paragraph',
  table: 'Table',
  // "Image", not "Figure": the index is Docling's picture count, so it
  // rarely matches the paper's own figure numbering, and "Figure 3" invited
  // a search for a figure the paper calls something else.
  figure: 'Image',
}

/** A short human label, counted from one: 'paragraph-53' -> "Paragraph 54",
 * 'table-1-row-7' -> "Table 2 · row 8 · p. 13", 'supp-figure-0' ->
 * "Supplement · Image 1". The page is appended when known (the supplement
 * has none, nor does a paper that is not parsed yet). */
export function describeAnchor(id: string, page?: number): string {
  const parsed = parseAnchor(id)
  if (!parsed) return id
  const parts = [`${KIND_LABEL[parsed.kind]} ${parsed.index + 1}`]
  if (parsed.supplement) parts.unshift('Supplement')
  if (parsed.row !== null) parts.push(`row ${parsed.row + 1}`)
  if (page !== undefined) parts.push(`p. ${page}`)
  return parts.join(' · ')
}
