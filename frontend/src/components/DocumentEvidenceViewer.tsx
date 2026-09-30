/* The evidence sheet's "Markdown" tab for evidence that cites anchors: the
 * paper's anchored markdown (GET /papers/{id}/document -- the exact text the
 * agents read and cited, main paper then supplement), with every cited block
 * highlighted by its id and the first scrolled into view. Nothing is
 * re-found: a `[paragraph-54]` tag in the source names the block, and a
 * citation's quote only ever *narrows* the highlight inside that block (a
 * <mark> around the quoted span); a quote that cannot be located leaves the
 * whole block highlighted. Rows, tables and figures never narrow.
 *
 * How the ids get from the source to the DOM: the tag stays in the text and
 * react-markdown's custom components read it back off the hast `node` they
 * are handed (react-markdown 10 passes `node` after every rehype plugin has
 * run), strip it from what they render, and set `data-anchor` /
 * `data-evidence-highlight` as React props -- which rehype-sanitize never
 * sees, so the GitHub default schema (plus `mark`, for the quote splice; see
 * lib/markdown.ts) stays exactly as strict. Tables carry their row ids
 * in a leading `anchor` column; the `tr` component drops that cell so it is
 * never shown.
 *
 * One prep pass over the source does the two things components cannot:
 * separates consecutive tag lines (list items) with a blank line so each
 * becomes its own <p> instead of one merged paragraph, and splices the
 * <mark> for quote narrowing inside the cited paragraph's own lines only.
 *
 * Known limitation: a fenced code block puts its tag on a line of its own
 * (see anchors.py's _tagged), so its highlight lands on that tag-only
 * paragraph above the <pre>. Docling emits these only for code/formula items.
 */
import { Children, useEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import type { Components, ExtraProps } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import { AlertCircle } from 'lucide-react'
import { paperDocumentPapersPaperIdDocumentGet } from '@/api/generated'
import type { Citation } from '@/api/generated'
import { apiErrorMessage } from '@/lib/apiError'
import { describeAnchor, parseAnchor, tableOfRow } from '@/lib/anchors'
import { Spinner } from '@/components/ui/spinner'
import { SANITIZE_SCHEMA, findWhitespaceTolerantMatch, resolveImageSrc, withHighlight } from '@/lib/markdown'
import type { TextMatch } from '@/lib/markdown'

type HastElement = NonNullable<ExtraProps['node']>
type HastNode = HastElement['children'][number]

// A block's leading tag: `[paragraph-54] text`, or `[figure-0]` alone on its line.
const TAG_RE = /^\[((?:supp-)?(?:paragraph|table|figure)-\d+)\](?:[ \t]|$)/
const ROW_ID_RE = /^(?:supp-)?table-\d+-row-\d+$/
const ANCHOR_COLUMN_HEADER = 'anchor'

function hastText(node: HastNode | undefined): string {
  if (!node) return ''
  if (node.type === 'text') return node.value
  if (node.type === 'element') return node.children.map(hastText).join('')
  return ''
}

function leadingAnchor(node: HastElement | undefined): string | null {
  const first = node?.children[0]
  return first?.type === 'text' ? (TAG_RE.exec(first.value)?.[1] ?? null) : null
}

/** The first cell's text, if it is a row id or the `anchor` column header. */
function anchorCell(tr: HastElement | undefined): string | null {
  const cell = tr?.children.find((child) => child.type === 'element')
  const text = hastText(cell).trim()
  return ROW_ID_RE.test(text) || text === ANCHOR_COLUMN_HEADER ? text : null
}

/* A <table> renders before any of its rows, so its id cannot come from
 * render-order state; the hast subtree is there up front, and the first row
 * id names the table. */
function tableAnchor(node: HastElement | undefined): string | null {
  if (!node) return null
  for (const child of node.children) {
    if (child.type !== 'element') continue
    if (child.tagName === 'tr') {
      const cell = anchorCell(child)
      if (cell && cell !== ANCHOR_COLUMN_HEADER) return tableOfRow(cell)
    }
    const nested = tableAnchor(child)
    if (nested) return nested
  }
  return null
}

function stripLeadingTag(children: ReactNode): ReactNode[] {
  const nodes = Children.toArray(children)
  const first = nodes[0]
  if (typeof first !== 'string') return nodes
  const rest = first.replace(TAG_RE, '')
  return rest ? [rest, ...nodes.slice(1)] : nodes.slice(1)
}

/* The markup lib/models/evidence_block.py's strip_markup removes from quotes
 * before they are stored: `<br>` becomes a space, a 1-2 letter <sup>/<sub>
 * (a footnote marker) is dropped, any other <sup>x</sup> becomes ^x and
 * <sub>x</sub> becomes _x, and a fixed list of tags is removed outright.
 * Mirrored here with an offset map so the quote (already stripped) can be
 * found in a block that still carries the markup, and the <mark> boundaries
 * mapped back to source offsets that never split a tag. */
const MARKUP_RE =
  /<br\s*\/?>|<(sup|sub)>([^<]+)<\/\1>|<\/?(?:br|sup|sub|b|i|em|strong|u|s|span|small|code|a|p|div|table|thead|tbody|tr|td|th|ul|ol|li)(?:\s[^<>]*)?\/?>/gi

function findQuoteInBlock(quote: string, text: string): TextMatch | null {
  let stripped = ''
  const starts: number[] = []
  const ends: number[] = []
  const push = (chunk: string, start: number, end: number) => {
    for (const ch of chunk) {
      stripped += ch
      starts.push(start)
      ends.push(end)
    }
  }
  let last = 0
  for (const match of text.matchAll(MARKUP_RE)) {
    for (let k = last; k < match.index; k++) push(text[k], k, k + 1)
    const [whole, tag, inner] = match
    let replacement = ''
    if (/^<br/i.test(whole)) replacement = ' '
    else if (tag && inner) {
      replacement = /^[A-Za-z]{1,2}$/.test(inner) ? '' : (tag.toLowerCase() === 'sup' ? '^' : '_') + inner
    }
    push(replacement, match.index, match.index + whole.length)
    last = match.index + whole.length
  }
  for (let k = last; k < text.length; k++) push(text[k], k, k + 1)
  const hit = findWhitespaceTolerantMatch(quote, stripped)
  return hit ? { start: starts[hit.start], end: ends[hit.end - 1] } : null
}

interface Prepared {
  markdown: string
  narrowed: Set<string> // paragraph ids whose quote was found and marked
}

const SUPPLEMENT_DIVIDER = '\n\n# Supplementary Material\n\n'

function prepareDocument(main: string, supplement: string | null | undefined, citations: Citation[]): Prepared {
  const source = supplement ? `${main}${SUPPLEMENT_DIVIDER}${supplement}` : main
  const quotes = new Map<string, string>()
  for (const citation of citations) {
    const quote = citation.quote?.trim()
    if (quote && parseAnchor(citation.anchor)?.kind === 'paragraph') quotes.set(citation.anchor, quote)
  }

  const lines = source.split('\n')
  const out: string[] = []
  const narrowed = new Set<string>()
  let inFence = false
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (line.trimStart().startsWith('```')) {
      inFence = !inFence
      out.push(line)
      continue
    }
    const tag = inFence ? null : TAG_RE.exec(line)
    if (!tag) {
      out.push(line)
      continue
    }
    // A tag line follows a blank line, except list items (consecutive tag
    // lines): give each its own paragraph instead of one merged <p>.
    if (out.length > 0 && out[out.length - 1].trim() !== '') out.push('')
    const quote = quotes.get(tag[1])
    if (!quote) {
      out.push(line)
      continue
    }
    let j = i + 1 // the block: this line up to the next blank line or fence
    while (j < lines.length && lines[j].trim() !== '' && !lines[j].startsWith('```')) j++
    const block = lines.slice(i, j).join('\n')
    const head = tag[0].length // never match inside the tag itself
    const hit = findQuoteInBlock(quote, block.slice(head))
    if (hit) {
      narrowed.add(tag[1])
      out.push(withHighlight(block, { start: hit.start + head, end: hit.end + head }))
    } else {
      out.push(block)
    }
    i = j - 1
  }
  return { markdown: out.join('\n'), narrowed }
}

export function DocumentEvidenceViewer({
  paperId,
  citations,
  enabled,
}: {
  paperId: number
  citations: Citation[]
  enabled: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  const query = useQuery({
    queryKey: ['document', paperId],
    queryFn: () =>
      paperDocumentPapersPaperIdDocumentGet({
        path: { paper_id: paperId },
        throwOnError: true,
      }),
    enabled,
  })
  const data = query.data

  const prepared = useMemo(
    () => (data ? prepareDocument(data.main, data.supplement, citations) : null),
    [data, citations]
  )
  const cited = useMemo(() => new Set(citations.map((citation) => citation.anchor)), [citations])
  const narrowed = prepared?.narrowed

  const components: Components = {
    p: ({ node, children, ...props }) => {
      const anchor = leadingAnchor(node)
      const content = anchor ? stripLeadingTag(children) : children
      const highlight = anchor !== null && cited.has(anchor) && !narrowed?.has(anchor)
      // A figure whose image is missing is `[figure-N] <!-- image -->`, and
      // sanitize drops the comment: say what the empty paragraph stands for.
      const empty = anchor !== null && Array.isArray(content) && content.length === 0
      return (
        <p {...props} data-anchor={anchor ?? undefined} data-evidence-highlight={highlight ? '' : undefined}>
          {empty ? (
            <span className="italic text-muted-foreground">{describeAnchor(anchor)} (no image)</span>
          ) : (
            content
          )}
        </p>
      )
    },
    // hast-util-to-jsx-runtime drops whitespace-only children of <tr>, so the
    // first rendered child is reliably the first cell.
    tr: ({ node, children, ...props }) => {
      const cells = Children.toArray(children)
      const cell = anchorCell(node)
      const anchor = cell && cell !== ANCHOR_COLUMN_HEADER ? cell : null
      const highlight = anchor !== null && cited.has(anchor)
      return (
        <tr {...props} data-anchor={anchor ?? undefined} data-evidence-highlight={highlight ? '' : undefined}>
          {cell ? cells.slice(1) : cells}
        </tr>
      )
    },
    table: ({ node, children, ...props }) => {
      const anchor = tableAnchor(node)
      const highlight = anchor !== null && cited.has(anchor)
      return (
        <table {...props} data-anchor={anchor ?? undefined} data-evidence-highlight={highlight ? '' : undefined}>
          {children}
        </table>
      )
    },
  }

  useEffect(() => {
    containerRef.current
      ?.querySelector('mark, [data-evidence-highlight]')
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [prepared])

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
        {apiErrorMessage(query.error, "Couldn't load this paper's text.")}
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
          [&_p[data-evidence-highlight]]:bg-yellow-200 [&_p[data-evidence-highlight]]:rounded
          [&_tr[data-evidence-highlight]>td]:bg-yellow-200
          [&_table[data-evidence-highlight]]:ring-2 [&_table[data-evidence-highlight]]:ring-yellow-300
          [&_p[data-evidence-highlight]_img]:rounded [&_p[data-evidence-highlight]_img]:ring-4 [&_p[data-evidence-highlight]_img]:ring-yellow-300"
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw, [rehypeSanitize, SANITIZE_SCHEMA]]}
          components={components}
          urlTransform={(url) => defaultUrlTransform(resolveImageSrc(url) ?? url)}
        >
          {prepared?.markdown ?? ''}
        </ReactMarkdown>
      </div>
    </div>
  )
}
