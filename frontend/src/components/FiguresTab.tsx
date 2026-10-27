/* The figures the Figure Description step described, one sub-tab per figure,
 * main text first: the kinds the step saw in it (a pedigree, a chromatogram,
 * a gel...), its image, the legend as printed and the vision model's reading.
 * A tab is named by the paper's own figure number when its legend starts with
 * one ("Figure 2.", "Fig. S1"), else by the figure's anchor in the paper text. */
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getFiguresPapersPaperIdFiguresGet } from '@/api/generated'
import type { FigureDescriptionResp } from '@/api/generated'
import { API_BASE_URL } from '@/lib/api'
import { describeAnchor } from '@/lib/anchors'
import type { CaptionSource } from '@/api/generated'
import { usePdfHighlight } from '@/components/PdfHighlightProvider'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const STALE_TIME = 5 * 60 * 1000

// "Figure 2.", "Fig. 1", "Supplementary Figure 3", "Figure S1": the paper's
// own number for the figure, at the head of its legend.
const FIGURE_NUMBER = /^\s*(?:(supplementa(?:ry|l)|suppl\.?)\s+)?fig(?:ure|\.)?\s*(S?\d+)/i

// How the legend under a figure was arrived at, in a reader's words: the
// paper's own text linked by the PDF parser or taken from beside the picture,
// or the vision model's pick of a nearby block or its reading of the image.
const SOURCE_LABEL: Record<CaptionSource, string> = {
  Docling: 'linked by the parser',
  'Adjacent text': 'taken from beside the figure',
  'Model chose': 'chosen by the vision model',
  'Model transcribed': 'transcribed from the image by the vision model',
}

/** The tab's name: the figure number its legend opens with, else its anchor. */
export function figureLabel(figure: Pick<FigureDescriptionResp, 'anchor' | 'caption'>): string {
  const match = figure.caption?.match(FIGURE_NUMBER)
  if (!match) return describeAnchor(figure.anchor)
  const number = match[2].toUpperCase()
  return match[1] && !number.startsWith('S') ? `Figure S${number}` : `Figure ${number}`
}

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
            {figureLabel(figure)}
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
      <figure className="flex flex-col items-center gap-2">
        <img
          src={`${API_BASE_URL}${figure.image_url}`}
          alt={figure.caption ?? figure.kinds.join(', ')}
          className="max-w-full rounded-lg border"
        />
        {figure.caption ? (
          <figcaption className="w-full text-sm text-foreground/80 leading-snug">
            {figure.caption}
            {figure.caption_source && (
              <span className="block mt-1 text-xs text-muted-foreground italic">
                Legend {SOURCE_LABEL[figure.caption_source]}
              </span>
            )}
          </figcaption>
        ) : (
          <figcaption className="w-full text-xs text-muted-foreground italic">
            No legend was attached to this figure in the parsed text.
          </figcaption>
        )}
      </figure>
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
