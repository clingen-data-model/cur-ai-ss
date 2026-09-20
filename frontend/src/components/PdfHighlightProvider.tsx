/* Lets any EvidencePopover on a paper's page open a PDF sheet scrolled to its
 * quote/table/figure. One sheet (and one pdfjs document) per page, provided
 * once near the root of the extraction page -- not one per popover, since
 * opening it is cheap but instantiating pdfjs per row would not be.
 *
 * Coordinates come from /grobid-annotation, which only reads word positions
 * and returns them -- unlike /highlight, it never writes to the shared
 * highlighted.pdf on disk, so this is safe for multiple curators to use at
 * the same time.
 */
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import * as pdfjs from 'pdfjs-dist'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { grobidAnnotationPapersPaperIdGrobidAnnotationPost } from '@/api/generated'
import { API_BASE_URL } from '@/lib/api'
import { apiErrorMessage } from '@/lib/apiError'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { PdfViewer, annotationsToHighlights, type Highlight, type PdfViewerRef } from '@/components/PdfViewer'

// Matches Streamlit's default palette (lib/ui/paper/shared.py's COLORS[0]) --
// this viewer is read-only, so there's no picker, just one fixed color.
const HIGHLIGHT_COLOR = '#FFF59D'

export interface HighlightTarget {
  quote?: string | null
  table_id?: number | null
  image_id?: number | null
}

interface PdfHighlightContextValue {
  openHighlight: (target: HighlightTarget) => void
}

const PdfHighlightContext = createContext<PdfHighlightContextValue | null>(null)

export function usePdfHighlight(): PdfHighlightContextValue {
  const ctx = useContext(PdfHighlightContext)
  if (!ctx) {
    throw new Error('usePdfHighlight must be used within a PdfHighlightProvider')
  }
  return ctx
}

function targetLabel(target: HighlightTarget): string {
  if (target.quote) return target.quote
  if (target.table_id != null) return `Table ${target.table_id}`
  if (target.image_id != null) return `Figure ${target.image_id}`
  return ''
}

export function PdfHighlightProvider({
  paperId,
  pdfUrl,
  children,
}: {
  paperId: number
  pdfUrl: string | undefined
  children: React.ReactNode
}) {
  const [target, setTarget] = useState<HighlightTarget | null>(null)
  const [highlights, setHighlights] = useState<Highlight[]>([])
  const pdfViewerRef = useRef<PdfViewerRef>(null)
  const fullPdfUrl = pdfUrl ? `${API_BASE_URL}${pdfUrl}` : ''

  const annotationsQuery = useQuery({
    queryKey: ['grobid-annotation', paperId, target],
    queryFn: () =>
      grobidAnnotationPapersPaperIdGrobidAnnotationPost({
        path: { paper_id: paperId },
        body: {
          queries: target?.quote ? [target.quote] : [],
          image_ids: target?.image_id != null ? [target.image_id] : [],
          table_ids: target?.table_id != null ? [target.table_id] : [],
          color: HIGHLIGHT_COLOR,
        },
        throwOnError: true,
      }),
    enabled: target !== null && fullPdfUrl !== '',
  })

  // annotationsToHighlights needs a loaded pdfjs document to look up each
  // page's viewport size -- loaded independently of PdfViewer's own PdfLoader
  // rather than threading a "document ready" callback through its ref, since
  // the browser serves the second fetch from cache.
  useEffect(() => {
    if (!annotationsQuery.data || annotationsQuery.data.length === 0 || !fullPdfUrl) {
      setHighlights([])
      return
    }
    let cancelled = false
    void (async () => {
      const doc = await pdfjs.getDocument(fullPdfUrl).promise
      const hs = await annotationsToHighlights(
        doc,
        annotationsQuery.data,
        targetLabel(target ?? {}),
      )
      if (cancelled) return
      setHighlights(hs)
      if (hs[0]) pdfViewerRef.current?.scrollTo(hs[0])
    })()
    return () => {
      cancelled = true
    }
  }, [annotationsQuery.data, fullPdfUrl, target])

  const openHighlight = (next: HighlightTarget) => {
    setHighlights([])
    setTarget(next)
  }

  const close = () => {
    setTarget(null)
    setHighlights([])
  }

  return (
    <PdfHighlightContext.Provider value={{ openHighlight }}>
      {children}
      <Sheet open={target !== null} onOpenChange={(open) => !open && close()}>
        <SheetContent side="right" className="data-[side=right]:sm:max-w-3xl">
          <SheetHeader className="border-b">
            <SheetTitle>View in PDF</SheetTitle>
          </SheetHeader>
          <div className="flex-1 min-h-0">
            {annotationsQuery.isPending ? (
              <div className="flex h-full items-center justify-center">
                <Spinner />
              </div>
            ) : annotationsQuery.isError ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
                <AlertCircle className="size-5" />
                {apiErrorMessage(annotationsQuery.error, "Couldn't locate this in the PDF.")}
              </div>
            ) : fullPdfUrl ? (
              <PdfViewer ref={pdfViewerRef} url={fullPdfUrl} highlights={highlights} />
            ) : null}
          </div>
        </SheetContent>
      </Sheet>
    </PdfHighlightContext.Provider>
  )
}
