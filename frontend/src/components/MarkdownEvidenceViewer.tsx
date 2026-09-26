/* The evidence sheet's "Markdown" tab: the paper's extracted markdown
 * (Docling's raw.md), with the evidence quote highlighted and scrolled into
 * view when a fuzzy match is found -- the text-based analog of the PDF
 * tab's coordinate-based highlight box.
 *
 * The match's character offsets come back from the backend already indexed
 * into this exact `content` string (see find_best_match_in_text), so a
 * literal `<mark>` is spliced into the markdown source before rendering.
 * rehype-raw is what lets ReactMarkdown treat that as an element rather than
 * literal text; rehype-sanitize (GitHub's default schema, plus `mark`) keeps
 * that raw-HTML door from also admitting anything unexpected already sitting
 * in a paper's markdown (Docling table conversion can leave stray literal
 * HTML in raw.md, the same reason lib/models/evidence_block.py strips markup
 * from quotes shown elsewhere in the UI).
 */
import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { AlertCircle } from 'lucide-react'
import { markdownAnnotationPapersPaperIdMarkdownAnnotationPost } from '@/api/generated'
import { apiErrorMessage } from '@/lib/apiError'
import { Spinner } from '@/components/ui/spinner'

const SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'mark'],
}

function withHighlight(content: string, match: { start: number; end: number } | null | undefined): string {
  if (!match) return content
  return content.slice(0, match.start) + '<mark>' + content.slice(match.start, match.end) + '</mark>' + content.slice(match.end)
}

export function MarkdownEvidenceViewer({
  paperId,
  quote,
  isSupplement,
  enabled,
}: {
  paperId: number
  quote: string | null | undefined
  isSupplement: boolean
  enabled: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  const query = useQuery({
    queryKey: ['markdown-annotation', paperId, quote, isSupplement],
    queryFn: () =>
      markdownAnnotationPapersPaperIdMarkdownAnnotationPost({
        path: { paper_id: paperId },
        body: { quote: quote ?? null, is_supplement: isSupplement },
        throwOnError: true,
      }),
    enabled,
  })

  const data = query.data

  useEffect(() => {
    if (!data?.match) return
    containerRef.current?.querySelector('mark')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [data])

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
          [&_mark]:rounded [&_mark]:px-0.5"
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw, [rehypeSanitize, SANITIZE_SCHEMA]]}
        >
          {withHighlight(data?.content ?? '', data?.match)}
        </ReactMarkdown>
      </div>
    </div>
  )
}
