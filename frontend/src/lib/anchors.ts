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
 * numbering, so a chip built from describeAnchor() says "Table 1 · row 7"
 * where the paper's caption may say "Table 2". That is why the chip also
 * carries the PDF page (GET /papers/{id}/anchor-pages): "Table 7 · row 3 ·
 * p. 13" is findable, "Table 7" alone is not.
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
  figure: 'Figure',
}

/** A short human label: "Paragraph 54", "Table 1 · row 7 · p. 13",
 * "Supplement · Figure 0". The page is appended when known (the supplement
 * has none, nor does a paper that is not parsed yet). */
export function describeAnchor(id: string, page?: number): string {
  const parsed = parseAnchor(id)
  if (!parsed) return id
  const parts = [`${KIND_LABEL[parsed.kind]} ${parsed.index}`]
  if (parsed.supplement) parts.unshift('Supplement')
  if (parsed.row !== null) parts.push(`row ${parsed.row}`)
  if (page !== undefined) parts.push(`p. ${page}`)
  return parts.join(' · ')
}
