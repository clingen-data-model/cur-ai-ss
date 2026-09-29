/* The evidence sheet's "Markdown" tab: the paper's extracted markdown
 * (Docling's raw.md), with the evidence quote highlighted and scrolled into
 * view when a match is found -- the text-based analog of the PDF tab's
 * coordinate-based highlight box. Like the PDF tab (which sends quote/
 * table_id/image_id to /grobid-annotation together and highlights whichever
 * are present, with no priority between them), table_id/image_id evidence
 * highlights the Nth table/image *alongside* the quote splice rather than
 * instead of it -- table_id also narrows to just the matching row when the
 * quote scores well against one, and the one exception is a quote whose
 * match itself falls inside that table's own raw text (see the comment
 * further down for why that one case still can't use the splice).
 *
 * Matching happens entirely client-side, against the plain `content` the
 * backend returns: a whitespace-tolerant exact match only, no fuzzy fallback
 * (see findWhitespaceTolerantMatch) -- an agent's quote is copied verbatim
 * from the paper, but Docling's markdown export can reproduce a justified
 * PDF's text layer with runs of 2+ raw spaces between words that a verbatim
 * quote collapses to one (confirmed on paper 27, PMID 8675681: "extended
 * kindred" in raw.md vs. "extended kindred" in the quote) -- so the quote's
 * own whitespace runs are matched loosely while everything else must line up
 * exactly. A miss just renders the plain markdown unhighlighted, same as
 * today -- this tab has always been best-effort.
 *
 * A literal `<mark>` is spliced into the markdown source at the match's
 * offsets before rendering. rehype-raw is what lets ReactMarkdown treat that
 * as an element rather than literal text; rehype-sanitize (GitHub's default
 * schema, plus `mark`) keeps that raw-HTML door from also admitting anything
 * unexpected already sitting in a paper's markdown (Docling table conversion
 * can leave stray literal HTML in raw.md, the same reason
 * lib/models/evidence_block.py strips markup from quotes shown elsewhere in
 * the UI).
 */
import { useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { AlertCircle } from 'lucide-react'
import { markdownAnnotationPapersPaperIdMarkdownAnnotationPost } from '@/api/generated'
import { apiErrorMessage } from '@/lib/apiError'
import { API_BASE_URL } from '@/lib/api'
import { Spinner } from '@/components/ui/spinner'

const SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'mark'],
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

interface TextMatch {
  start: number
  end: number
}

function findWhitespaceTolerantMatch(quote: string | null | undefined, text: string): TextMatch | null {
  const trimmed = quote?.trim()
  if (!trimmed || !text) return null
  const pattern = trimmed.split(/\s+/).map(escapeRegExp).join('\\s+')
  const match = new RegExp(pattern, 'i').exec(text)
  return match ? { start: match.index, end: match.index + match[0].length } : null
}

function withHighlight(content: string, match: TextMatch | null): string {
  if (!match) return content
  return content.slice(0, match.start) + '<mark>' + content.slice(match.start, match.end) + '</mark>' + content.slice(match.end)
}

interface GfmTable {
  rows: string[] // data row lines, in source order; header/separator excluded
  start: number // char offset of the table block's first line (its header row)
  end: number // char offset just past the table block's last line
}

const SEPARATOR_ROW = /^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/

function isTableRowLine(line: string | undefined): line is string {
  return !!line && line.includes('|') && line.trim().length > 0
}

/* A lightweight, string-level re-scan of the same GFM pipe tables
 * remark-gfm will parse -- just enough to isolate table_id's own data rows
 * (skipping its header/separator) so a row within it can be matched against
 * `quote`, without needing a round trip to re-derive this server-side. Table
 * order here only needs to agree with the order react-markdown renders
 * <table> elements in (trivially true -- both read top-to-bottom through the
 * same content), not with remark-gfm's parser internals.
 *
 * Also returns each table's raw character range, so a quote match that lands
 * inside one (as opposed to in the surrounding prose) can be detected and
 * kept out of the quote-splice highlight -- see overlapsAnyTable.
 */
function extractGfmTables(content: string): GfmTable[] {
  const lines = content.split('\n')
  const lineStarts: number[] = []
  let offset = 0
  for (const line of lines) {
    lineStarts.push(offset)
    offset += line.length + 1 // +1 for the '\n' this split consumed
  }

  const tables: GfmTable[] = []
  let i = 0
  while (i < lines.length) {
    if (isTableRowLine(lines[i]) && SEPARATOR_ROW.test(lines[i + 1] ?? '')) {
      const rows: string[] = []
      let j = i + 2
      while (isTableRowLine(lines[j])) {
        rows.push(lines[j])
        j += 1
      }
      const lastLine = j - 1
      tables.push({ rows, start: lineStarts[i], end: lineStarts[lastLine] + lines[lastLine].length })
      i = j
    } else {
      i += 1
    }
  }
  return tables
}

function overlapsAnyTable(match: TextMatch, tables: GfmTable[]): boolean {
  return tables.some((table) => match.start < table.end && match.end > table.start)
}

function normalizeForMatch(text: string): string {
  return text
    .toLowerCase()
    .replace(/[|_*`]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const MIN_ROW_MATCH_SCORE = 0.5

/* Word-overlap, not an edit-distance ratio like the backend's fuzzy quote
 * match -- there's no need to reproduce rapidfuzz here, just enough
 * confidence to prefer one row over its neighbors. quote is the row copied
 * verbatim (see core_extraction_rules.py's TABLE EVIDENCE RULES), so a
 * genuine match shares most of its distinctive (3+ letter) words with
 * exactly one row and few with the rest.
 */
function bestRowIndex(rows: string[], quote: string): number | null {
  const quoteWords = normalizeForMatch(quote)
    .split(' ')
    .filter((word) => word.length > 2)
  if (quoteWords.length === 0) return null

  let bestIndex: number | null = null
  let bestScore = 0
  rows.forEach((row, index) => {
    const rowWords = new Set(
      normalizeForMatch(row)
        .split(' ')
        .filter((word) => word.length > 2)
    )
    if (rowWords.size === 0) return
    const score = quoteWords.filter((word) => rowWords.has(word)).length / quoteWords.length
    if (score > bestScore) {
      bestScore = score
      bestIndex = index
    }
  })
  return bestScore >= MIN_ROW_MATCH_SCORE ? bestIndex : null
}

/* Docling writes each figure's `src` as the absolute filesystem path it saved
 * the image to on the API host (e.g. `/var/caa/extracted_pdfs/20/raw_artifacts/
 * image_000002_<hash>.png`) -- the same kind of server-relative path the API
 * returns for thumbnail_url/pdf_url/avatar_url, which every other caller in
 * this app resolves by prefixing API_BASE_URL (see PedigreeTab.tsx). Left
 * alone, the browser instead resolves it against the SPA's own origin.
 */
function resolveImageSrc(src: string | undefined): string | undefined {
  return src?.startsWith('/') ? `${API_BASE_URL}${src}` : src
}

export function MarkdownEvidenceViewer({
  paperId,
  quote,
  tableId,
  imageId,
  isSupplement = false,
  enabled,
}: {
  paperId: number
  quote: string | null | undefined
  tableId?: number | null
  imageId?: number | null
  isSupplement?: boolean
  enabled: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  const query = useQuery({
    queryKey: ['markdown-annotation', paperId, isSupplement],
    queryFn: () =>
      markdownAnnotationPapersPaperIdMarkdownAnnotationPost({
        path: { paper_id: paperId },
        body: { is_supplement: isSupplement },
        throwOnError: true,
      }),
    enabled,
  })

  const data = query.data

  /* table_id/image_id have no offsets of their own -- unlike a quote, there's
   * nothing to splice a literal <mark> around without risking a GFM table
   * (a raw HTML tag straddling a pipe-table's lines can make remark stop
   * parsing it as a table at all). Docling's PDF-side highlighting already
   * trusts table_id/image_id as a plain 0-based position among the
   * document's tables/pictures in order (lib/misc/pdf/highlight.py's
   * figures_to_grobid_annotations indexes docling's own JSON dump the same
   * way) -- so here that same ordinal is used to find the Nth <table>/<img>
   * as react-markdown renders them, and that whole element gets a
   * data-evidence-highlight attribute (styled below) instead of a <mark>
   * wrapper -- both are block/replaced content that a real <mark> node
   * doesn't reliably highlight (an inline <mark> around a block <table>
   * splits into two empty boxes rather than covering it; around an opaque
   * <img> its background just sits behind the image, invisible).
   *
   * table_id evidence never uses the quote-splice highlight for a match that
   * falls *inside* a table's own raw text, even though agents are often told
   * to copy the table row verbatim into quote: such a match commonly spans
   * several `|`-delimited cells, and each cell's inline content is parsed
   * independently -- a <mark> opened in one cell has no matching close until
   * deep in a later cell, so it silently closes at the first cell boundary
   * instead, leaving only a sliver of the first cell highlighted rather than
   * the row (confirmed live against paper 83's patient 993). A quote can
   * still be prose that merely *references* a table (e.g. "...were
   * identified in patient B430 and B546 (Table 2)" -- paper 13's patient
   * B546), which lives outside any table's raw text and splices in exactly
   * like any other quote -- overlapsAnyTable is what tells these two cases
   * apart, so both the prose mention and the table/row can be highlighted
   * together. image_id evidence has no such risk (a quote next to a figure
   * is plain prose, with no cell boundaries to straddle), so it always
   * highlights alongside the quote splice.
   */
  const highlightTableId = tableId ?? null
  const tables = useMemo(() => extractGfmTables(data?.content ?? ''), [data?.content])
  const spliceMatch = useMemo(() => {
    const match = findWhitespaceTolerantMatch(quote, data?.content ?? '')
    return match && !overlapsAnyTable(match, tables) ? match : null
  }, [quote, data?.content, tables])
  const highlightImageId = imageId ?? null

  /* When there's a quote to go with table_id, try to pin down which row of
   * that specific table it came from -- a much more useful highlight than
   * the whole table, and (unlike the in-table quote-splice this replaces)
   * safe because it's applied to a whole rendered <tr>, never split
   * mid-cell. Falls back to null (whole-table highlight) whenever there's no
   * quote or no row scores confidently enough.
   */
  const targetTableRows = highlightTableId != null ? (tables[highlightTableId]?.rows ?? null) : null
  const targetRowIndex =
    targetTableRows && quote ? bestRowIndex(targetTableRows, quote) : null

  let tableIndex = 0
  let imageIndex = 0
  let currentTableIsTarget = false
  let rowsSeenInCurrentTable = 0
  const components: Components = {
    // Whole-table fallback uses the same data-attribute technique as the
    // <tr> case below rather than <mark> -- <mark> is inline content and
    // <table> is block-level, so the browser splits the inline box around
    // it into two empty (background-only) boxes rather than covering the
    // table, leaving a stray colored sliver just above and below it instead
    // of highlighting anything (confirmed live on paper 13's Table 2).
    table: ({ children, ...props }) => {
      currentTableIsTarget = tableIndex === highlightTableId
      rowsSeenInCurrentTable = 0
      tableIndex += 1
      const isWholeTableTarget = currentTableIsTarget && targetRowIndex == null
      return (
        <table {...props} data-evidence-highlight={isWholeTableTarget ? '' : undefined}>
          {children}
        </table>
      )
    },
    // GFM tables have exactly one header row, always first -- everything
    // after it is a data row, so "seen index 0" needs no thead/tbody check.
    tr: ({ children, ...props }) => {
      const seenIndex = rowsSeenInCurrentTable
      rowsSeenInCurrentTable += 1
      const isTargetRow = currentTableIsTarget && seenIndex - 1 === targetRowIndex
      return (
        <tr {...props} data-evidence-highlight={isTargetRow ? '' : undefined}>
          {children}
        </tr>
      )
    },
    // Same data-attribute technique as tr/table above, not <mark>: an <img>
    // is inline-replaced content, so wrapping it in <mark> mostly just tints
    // the mark's own px-0.5 padding either side of the image -- the image
    // itself covers the rest of the box, hiding a background-color highlight
    // behind it. A border/box-shadow (styled below) stays visible over an
    // opaque image where a background wouldn't.
    img: ({ src, ...props }) => {
      const isTarget = imageIndex === highlightImageId
      imageIndex += 1
      return <img src={resolveImageSrc(src)} {...props} data-evidence-highlight={isTarget ? '' : undefined} />
    },
  }

  useEffect(() => {
    containerRef.current
      ?.querySelector('mark, [data-evidence-highlight]')
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [data, tableId, imageId, quote])

  if (query.isPending) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
        <AlertCircle className="size-5" />
        {apiErrorMessage(query.error, "Couldn't load this paper's markdown.")}
      </div>
    )
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto p-6">
      <div
        className="max-w-3xl mx-auto text-sm
          [&_h1]:text-lg [&_h1]:font-semibold [&_h1]:mt-4 [&_h1]:mb-2
          [&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-4 [&_h2]:mb-2
          [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-3 [&_h3]:mb-1
          [&_p]:my-2 [&_strong]:font-medium
          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2
          [&_li]:my-0.5 [&_table]:border-collapse [&_table]:my-2
          [&_th]:border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:px-2 [&_td]:py-1
          [&_mark]:rounded [&_mark]:px-0.5
          [&_tr[data-evidence-highlight]>td]:bg-yellow-200
          [&_table[data-evidence-highlight]_td]:bg-yellow-200 [&_table[data-evidence-highlight]_th]:bg-yellow-200
          [&_img[data-evidence-highlight]]:rounded [&_img[data-evidence-highlight]]:ring-4 [&_img[data-evidence-highlight]]:ring-yellow-300"
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw, [rehypeSanitize, SANITIZE_SCHEMA]]}
          components={components}
        >
          {withHighlight(data?.content ?? '', spliceMatch)}
        </ReactMarkdown>
      </div>
    </div>
  )
}
