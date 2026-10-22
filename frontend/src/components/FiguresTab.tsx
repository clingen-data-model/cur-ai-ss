/* The figures the Figure Description step described: each one's image, the
 * kinds the step saw in it (a pedigree, a chromatogram, a gel...) and the
 * vision model's reading, main text first. The label over each figure is
 * its anchor in the paper text, not the paper's own figure number. */
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getFiguresPapersPaperIdFiguresGet } from '@/api/generated'
import type { FigureDescriptionResp } from '@/api/generated'
import { API_BASE_URL } from '@/lib/api'
import { describeAnchor } from '@/lib/anchors'
import { usePdfHighlight } from '@/components/PdfHighlightProvider'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'

const STALE_TIME = 5 * 60 * 1000

export function FiguresTab({ paperId }: { paperId: number }) {
  const { data: figures, isPending } = useQuery({
    queryKey: ['figures', paperId],
    queryFn: () => getFiguresPapersPaperIdFiguresGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  if (isPending) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  if (!figures || figures.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No described figures. The Figure Description step describes the figures that show a
        pedigree or genotyping evidence; re-run it from Rerun Agents to read this paper's figures.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-10 max-w-2xl mx-auto py-2">
      {figures.map((figure) => (
        <DescribedFigure key={figure.anchor} figure={figure} />
      ))}
    </div>
  )
}

function DescribedFigure({ figure }: { figure: FigureDescriptionResp }) {
  const { anchorPage } = usePdfHighlight()
  return (
    <section className="flex flex-col items-center gap-4">
      <div className="w-full flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium" title={figure.anchor}>
          {describeAnchor(figure.anchor, anchorPage(figure.anchor))}
        </span>
        {figure.kinds.map((kind) => (
          <Badge key={kind} variant="outline" className="font-normal text-muted-foreground">
            {kind}
          </Badge>
        ))}
      </div>
      <img
        src={`${API_BASE_URL}${figure.image_url}`}
        alt={figure.kinds.join(', ')}
        className="max-w-full rounded-lg border"
      />
      <div
        className="w-full text-sm text-muted-foreground
          [&_h1]:text-base [&_h1]:font-semibold [&_h1]:text-foreground [&_h1]:mt-3 [&_h1]:mb-1
          [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:text-foreground [&_h2]:mt-3 [&_h2]:mb-1
          [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-foreground [&_h3]:mt-2 [&_h3]:mb-1
          [&_p]:my-1.5 [&_strong]:text-foreground [&_strong]:font-medium
          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1.5
          [&_li]:my-0.5 [&_table]:border-collapse [&_table]:my-2
          [&_th]:border [&_th]:px-2 [&_th]:py-1 [&_th]:text-foreground [&_td]:border [&_td]:px-2 [&_td]:py-1"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{figure.description}</ReactMarkdown>
      </div>
    </section>
  )
}
