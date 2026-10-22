/* The figures the Figure Description step described, one sub-tab per figure,
 * main text first: the kinds the step saw in it (a pedigree, a chromatogram,
 * a gel...), its image and the vision model's reading. Each tab is named by
 * the figure's anchor in the paper text, not the paper's own figure number. */
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

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

  // The list is keyed by paper, so a re-run that describes a different set of
  // figures remounts the tabs and the first figure is selected again.
  return (
    <Tabs key={figures.map((figure) => figure.anchor).join()} defaultValue={figures[0].anchor}>
      <TabsList variant="line">
        {figures.map((figure) => (
          <TabsTrigger key={figure.anchor} value={figure.anchor} title={figure.anchor}>
            {describeAnchor(figure.anchor)}
          </TabsTrigger>
        ))}
      </TabsList>
      {figures.map((figure) => (
        <TabsContent key={figure.anchor} value={figure.anchor} className="pt-3">
          <DescribedFigure figure={figure} />
        </TabsContent>
      ))}
    </Tabs>
  )
}

function DescribedFigure({ figure }: { figure: FigureDescriptionResp }) {
  const { anchorPage } = usePdfHighlight()
  const page = anchorPage(figure.anchor)
  return (
    <section className="flex flex-col items-center gap-4 max-w-2xl mx-auto">
      <div className="w-full flex flex-wrap items-center gap-2">
        {figure.kinds.map((kind) => (
          <Badge key={kind} variant="outline" className="font-normal text-muted-foreground">
            {kind}
          </Badge>
        ))}
        {page !== undefined && (
          <span className="ml-auto text-xs text-muted-foreground">p. {page}</span>
        )}
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
