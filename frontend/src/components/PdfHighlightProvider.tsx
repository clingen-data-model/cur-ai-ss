/* Lets any EvidencePopover on a paper's page open a PDF sheet scrolled to its
 * evidence. One sheet (and one pdfjs document) per page, provided once near
 * the root of the extraction page -- not one per popover, since opening it is
 * cheap but instantiating pdfjs per row would not be.
 *
 * Two kinds of evidence, two backends, one sheet:
 *
 * - Evidence that cites anchors (`citations`, everything extracted since
 *   slice 2 of docs/evidence-anchors-plan.md) posts them to /highlight, which
 *   returns the cited blocks' precomputed boxes, and renders the anchored
 *   document (DocumentEvidenceViewer) on the Markdown tab.
 * - Legacy evidence (quote/table_id/image_id, papers not re-extracted yet)
 *   goes through /grobid-annotation and MarkdownEvidenceViewer unchanged;
 *   that path goes away in slice 4.
 *
 * Neither writes anything on disk, so this is safe for several curators at
 * once.
 */
import { createContext, useContext, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import {
  grobidAnnotationPapersPaperIdGrobidAnnotationPost,
  highlightCitationsPapersPaperIdHighlightPost,
} from '@/api/generated'
import type { Citation, GrobidAnnotation } from '@/api/generated'
import { API_BASE_URL } from '@/lib/api'
import { apiErrorMessage } from '@/lib/apiError'
import { isSupplementAnchor } from '@/lib/anchors'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PdfViewer } from '@/components/PdfViewer'
import { MarkdownEvidenceViewer } from '@/components/MarkdownEvidenceViewer'
import { DocumentEvidenceViewer } from '@/components/DocumentEvidenceViewer'

type ViewerTab = 'pdf' | 'markdown'

// Matches Streamlit's default palette (lib/ui/paper/shared.py's COLORS[0]) --
// this viewer is read-only, so there's no picker, just one fixed color.
const HIGHLIGHT_COLOR = '#FFF59D'

export interface LegacyHighlightTarget {
  quote?: string | null
  table_id?: number | null
  image_id?: number | null
  // Supplement evidence has no PDF/words.json of its own (see EvidencePopover) --
  // there's a separate raw.md for it, so this opens straight to the Markdown tab
  // with the PDF tab disabled, rather than the coordinate-based PDF tab.
  is_supplement?: boolean
}

export interface CitationHighlightTarget {
  citations: Citation[]
}

export type HighlightTarget = LegacyHighlightTarget | CitationHighlightTarget

function isCitationTarget(target: HighlightTarget): target is CitationHighlightTarget {
  return 'citations' in target
}

/** True when nothing about this evidence can be shown on the PDF (supplement only). */
export function isSupplementOnly(target: HighlightTarget): boolean {
  return isCitationTarget(target)
    ? target.citations.every((citation) => isSupplementAnchor(citation.anchor))
    : !!target.is_supplement
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

function fetchAnnotations(paperId: number, target: HighlightTarget): Promise<GrobidAnnotation[]> {
  if (isCitationTarget(target)) {
    return highlightCitationsPapersPaperIdHighlightPost({
      path: { paper_id: paperId },
      body: { citations: target.citations, color: HIGHLIGHT_COLOR },
      throwOnError: true,
    })
  }
  return grobidAnnotationPapersPaperIdGrobidAnnotationPost({
    path: { paper_id: paperId },
    body: {
      queries: target.quote ? [target.quote] : [],
      image_ids: target.image_id != null ? [target.image_id] : [],
      table_ids: target.table_id != null ? [target.table_id] : [],
      color: HIGHLIGHT_COLOR,
    },
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
    queryKey: ['grobid-annotation', paperId, target],
    queryFn: () => fetchAnnotations(paperId, target as HighlightTarget),
    enabled: target !== null && !supplementOnly && fullPdfUrl !== '' && activeTab === 'pdf',
  })

  const openHighlight = (next: HighlightTarget) => {
    setTarget(next)
    setActiveTab(isSupplementOnly(next) ? 'markdown' : 'pdf')
  }

  const close = () => {
    setTarget(null)
  }

  return (
    <PdfHighlightContext.Provider value={{ openHighlight }}>
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
              {target && isCitationTarget(target) ? (
                <DocumentEvidenceViewer
                  paperId={paperId}
                  citations={target.citations}
                  enabled={activeTab === 'markdown'}
                />
              ) : (
                <MarkdownEvidenceViewer
                  paperId={paperId}
                  quote={target?.quote}
                  tableId={target?.table_id}
                  imageId={target?.image_id}
                  isSupplement={target?.is_supplement}
                  enabled={target !== null && activeTab === 'markdown'}
                />
              )}
            </TabsContent>
          </Tabs>
        </SheetContent>
      </Sheet>
    </PdfHighlightContext.Provider>
  )
}
