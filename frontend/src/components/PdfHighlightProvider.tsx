/* Lets any EvidencePopover on a paper's page open a PDF sheet scrolled to its
 * evidence. One sheet (and one pdfjs document) per page, provided once near
 * the root of the extraction page -- not one per popover, since opening it is
 * cheap but instantiating pdfjs per row would not be.
 *
 * Evidence is a list of citations ({anchor, quote}, see
 * docs/evidence-anchors-plan.md). The PDF tab posts them to /highlight, which
 * returns the cited blocks' precomputed boxes; the Markdown tab renders the
 * anchored document (DocumentEvidenceViewer) with the cited blocks
 * highlighted by id. Neither writes anything on disk, so this is safe for
 * several curators at once.
 */
import { createContext, useContext, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import {
  highlightCitationsPapersPaperIdHighlightPost,
  paperAnchorPagesPapersPaperIdAnchorPagesGet,
} from '@/api/generated'
import type { Citation, GrobidAnnotation } from '@/api/generated'
import { API_BASE_URL } from '@/lib/api'
import { apiErrorMessage } from '@/lib/apiError'
import { isSupplementAnchor, tableOfRow } from '@/lib/anchors'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PdfViewer } from '@/components/PdfViewer'
import { DocumentEvidenceViewer } from '@/components/DocumentEvidenceViewer'

type ViewerTab = 'pdf' | 'markdown'

// Matches Streamlit's default palette (lib/ui/paper/shared.py's COLORS[0]) --
// this viewer is read-only, so there's no picker, just one fixed color.
const HIGHLIGHT_COLOR = '#FFF59D'

export interface HighlightTarget {
  citations: Citation[]
}

/** True when nothing about this evidence can be shown on the PDF: every
 * citation points into the supplement, which has no PDF view of its own, so
 * the sheet opens straight to the Markdown tab with the PDF tab disabled. */
export function isSupplementOnly(target: HighlightTarget): boolean {
  return (
    target.citations.length > 0 && target.citations.every((citation) => isSupplementAnchor(citation.anchor))
  )
}

interface PdfHighlightContextValue {
  openHighlight: (target: HighlightTarget) => void
  /** The PDF page an anchor is on, for the evidence chips (undefined for a
   * supplement anchor, an unparsed paper, or while the map is loading). */
  anchorPage: (anchor: string) => number | undefined
}

const PdfHighlightContext = createContext<PdfHighlightContextValue | null>(null)

export function usePdfHighlight(): PdfHighlightContextValue {
  const ctx = useContext(PdfHighlightContext)
  if (!ctx) {
    throw new Error('usePdfHighlight must be used within a PdfHighlightProvider')
  }
  return ctx
}

function fetchAnnotations(paperId: number, target: HighlightTarget): Promise<GrobidAnnotation[]> {
  return highlightCitationsPapersPaperIdHighlightPost({
    path: { paper_id: paperId },
    body: { citations: target.citations, color: HIGHLIGHT_COLOR },
    throwOnError: true,
  })
}

export function PdfHighlightProvider({
  paperId,
  pdfUrl,
  filename,
  children,
}: {
  paperId: number
  pdfUrl: string | undefined
  filename?: string | null
  children: React.ReactNode
}) {
  const [target, setTarget] = useState<HighlightTarget | null>(null)
  const [activeTab, setActiveTab] = useState<ViewerTab>('pdf')
  const fullPdfUrl = pdfUrl ? `${API_BASE_URL}${pdfUrl}` : ''
  const supplementOnly = target !== null && isSupplementOnly(target)

  const annotationsQuery = useQuery({
    queryKey: ['highlight', paperId, target],
    queryFn: () => fetchAnnotations(paperId, target as HighlightTarget),
    enabled: target !== null && !supplementOnly && fullPdfUrl !== '' && activeTab === 'pdf',
  })

  // One small map per paper (anchor id -> page), fetched once so every
  // popover on the page can label its chips without a request of its own.
  // It only changes when PDF parsing re-runs, hence the long staleTime.
  const pagesQuery = useQuery({
    queryKey: ['anchor-pages', paperId],
    queryFn: () =>
      paperAnchorPagesPapersPaperIdAnchorPagesGet({ path: { paper_id: paperId }, throwOnError: true }),
    staleTime: 5 * 60 * 1000,
  })
  // A row is on its table's page (the map lists items, not rows).
  const anchorPage = (anchor: string) => pagesQuery.data?.[tableOfRow(anchor)]

  const openHighlight = (next: HighlightTarget) => {
    setTarget(next)
    setActiveTab(isSupplementOnly(next) ? 'markdown' : 'pdf')
  }

  const close = () => {
    setTarget(null)
  }

  return (
    <PdfHighlightContext.Provider value={{ openHighlight, anchorPage }}>
      {children}
      <Sheet open={target !== null} onOpenChange={(open) => !open && close()}>
        <SheetContent
          side="right"
          showCloseButton={false}
          className="gap-0 data-[side=right]:sm:max-w-3xl"
        >
          {/* The viewer's own toolbar carries the close button, so the sheet
            * needs only one row -- but the dialog still needs an accessible
            * name. */}
          <SheetTitle className="sr-only">View evidence</SheetTitle>
          <Tabs
            value={activeTab}
            onValueChange={(value) => setActiveTab(value as ViewerTab)}
            className="flex-1 min-h-0 flex flex-col gap-0"
          >
            <TabsList className="mx-4 mt-3 w-fit">
              <TabsTrigger value="pdf" disabled={supplementOnly}>
                PDF
              </TabsTrigger>
              <TabsTrigger value="markdown">Markdown</TabsTrigger>
            </TabsList>
            <TabsContent value="pdf" className="flex-1 min-h-0">
              {supplementOnly ? (
                <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
                  This evidence came from the paper's supplement, which has no PDF view.
                </div>
              ) : annotationsQuery.isPending ? (
                <div className="flex h-full items-center justify-center">
                  <Spinner />
                </div>
              ) : annotationsQuery.isError ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
                  <AlertCircle className="size-5" />
                  {apiErrorMessage(annotationsQuery.error, "Couldn't locate this in the PDF.")}
                </div>
              ) : fullPdfUrl ? (
                <PdfViewer
                  url={fullPdfUrl}
                  filename={filename}
                  annotations={annotationsQuery.data ?? []}
                  onClose={close}
                />
              ) : null}
            </TabsContent>
            <TabsContent value="markdown" className="flex-1 min-h-0">
              {target && (
                <DocumentEvidenceViewer
                  paperId={paperId}
                  citations={target.citations}
                  enabled={activeTab === 'markdown'}
                />
              )}
            </TabsContent>
          </Tabs>
        </SheetContent>
      </Sheet>
    </PdfHighlightContext.Provider>
  )
}
