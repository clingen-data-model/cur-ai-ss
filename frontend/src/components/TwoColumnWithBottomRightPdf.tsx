import React, { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import { PdfHighlighter, PdfLoader, Highlight as PdfHighlight } from 'react-pdf-highlighter'
import 'react-pdf-highlighter/dist/style.css'
import * as pdfjs from 'pdfjs-dist'
import { Spinner } from '@/components/ui/spinner'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import type { GrobidAnnotation } from '@/api/generated/types.gen'

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`

export interface Highlight {
  id: string
  content: { text: string }
  position: {
    boundingRect: {
      x1: number
      y1: number
      x2: number
      y2: number
      width: number
      height: number
      pageNumber: number
    }
    rects: Array<{
      x1: number
      y1: number
      x2: number
      y2: number
      width: number
      height: number
      pageNumber: number
    }>
    pageNumber: number
  }
  comment: { text: string; emoji: string }
}

export async function annotationsToHighlights(
  pdfDocument: pdfjs.PDFDocumentProxy,
  annotations: GrobidAnnotation[],
  text: string,
): Promise<Highlight[]> {
  if (annotations.length === 0) return []

  const byPage = new Map<number, GrobidAnnotation[]>()
  for (const a of annotations) {
    if (!byPage.has(a.page)) byPage.set(a.page, [])
    byPage.get(a.page)!.push(a)
  }

  const highlights: Highlight[] = []
  for (const [pageNumber, anns] of byPage.entries()) {
    try {
      const page = await pdfDocument.getPage(pageNumber)
      const viewport = page.getViewport({ scale: 1 })
      const pageWidth = viewport.width
      const pageHeight = viewport.height

      // GROBID coords are PDF points (matches scale=1 viewport)
      // Use absolute coordinates with viewport dimensions as width/height
      const rects = anns.map((a) => ({
        x1: a.x,
        y1: a.y,
        x2: a.x + a.width,
        y2: a.y + a.height,
        width: pageWidth,
        height: pageHeight,
        pageNumber,
      }))

      const x1 = Math.min(...rects.map((r) => r.x1))
      const y1 = Math.min(...rects.map((r) => r.y1))
      const x2 = Math.max(...rects.map((r) => r.x2))
      const y2 = Math.max(...rects.map((r) => r.y2))

      highlights.push({
        id: `${text}-${pageNumber}`,
        content: { text },
        position: {
          boundingRect: {
            x1,
            y1,
            x2,
            y2,
            width: pageWidth,
            height: pageHeight,
            pageNumber,
          },
          rects,
          pageNumber,
        },
        comment: { text: '', emoji: '' },
      })
    } catch (err) {
      console.error(`Failed to process page ${pageNumber}:`, err)
    }
  }
  return highlights
}

export interface PdfViewerRef {
  scrollTo: (highlight: Highlight) => void
  pdfDocument: pdfjs.PDFDocumentProxy | null
}

interface PdfViewerProps {
  url: string
  highlights: Highlight[]
}

// forwardRef: the `ref` arg only arrives via the literal `ref={}` attribute at the
// call site (e.g. <PdfViewer ref={pdfViewerRef} />). `ref` is a reserved prop name —
// passing it under any other name (pdfViewRef={...}) would land in props, not here.
const PdfViewer = forwardRef<PdfViewerRef, PdfViewerProps>(
  ({ url, highlights }, ref) => {
    // Both values are produced inside PdfLoader/PdfHighlighter render-prop callbacks,
    // where setState isn't allowed — so refs are the right fit, not state.
    const scrollToRef = useRef<((h: Highlight) => void) | null>(null)
    const pdfDocRef = useRef<pdfjs.PDFDocumentProxy | null>(null)

    // Override what the parent gets from `ref.current`: instead of a DOM node,
    // expose a custom handle with scrollTo + pdfDocument.
    // Getters read the refs lazily, so the parent always sees the latest values.
    useImperativeHandle(ref, () => ({
      scrollTo: (highlight: Highlight) => {
        if (scrollToRef.current) {
          scrollToRef.current(highlight)
        }
      },
      get pdfDocument() {
        return pdfDocRef.current
      },
    }))


    return (
      // Single position:relative container with a real height — the library's PDF
      // container is position:absolute/height:100% and resolves against this. An extra
      // wrapper here can starve it of height at mount, so pagesinit never fires.
      <div style={{ position: 'relative', height: '100%', width: '100%' }}>
        <PdfLoader url={url} beforeLoad={<Spinner />}>
            {(loadedDocument) => {
              // Store the loaded doc so the imperative handle can expose it
              pdfDocRef.current = loadedDocument
              return (
                <PdfHighlighter
                  pdfDocument={loadedDocument}
                  scrollRef={(scrollTo) => {
                    scrollToRef.current = scrollTo
                  }}
                  // Disable area highlighting (Alt+drag rectangle selection)
                  enableAreaSelection={() => false}
                  onScrollChange={() => {}}
                  highlights={highlights}
                  // Disable commenting (no popup when text is selected)
                  onSelectionFinished={() => null}
                  // Render each highlight: called once per highlight in the highlights array
                  highlightTransform={(highlight, index) => (
                    <PdfHighlight
                      key={highlight.id ?? index}
                      isScrolledTo={false}
                      position={highlight.position}
                      comment={highlight.comment}
                    />
                  )}
                />
              )
            }}
          </PdfLoader>
      </div>
    )
  },
)

PdfViewer.displayName = 'PdfViewer'

interface TwoColumnWithBottomRightPdfProps {
  left: React.ReactNode
  leftDefaultSize?: number
  leftMinSize?: number
  topRight: React.ReactNode
  topRightDefaultSize?: number
  topRightMinSize?: number
  pdfUrl: string
  pdfHighlights: Highlight[]
  pdfViewerRef?: React.Ref<PdfViewerRef>
  bottomRightDefaultSize?: number
  bottomRightMinSize?: number
}

export function TwoColumnWithBottomRightPdf({
  left,
  leftDefaultSize = 33,
  leftMinSize = 20,
  topRight,
  topRightDefaultSize = 50,
  topRightMinSize = 50,
  pdfUrl,
  pdfHighlights,
  pdfViewerRef,
  bottomRightDefaultSize = 50,
  bottomRightMinSize = 50,
}: TwoColumnWithBottomRightPdfProps) {
  return (
    <div className="h-[calc(100vh-8rem)] p-4">
      <ResizablePanelGroup orientation="horizontal" className="h-full rounded-lg border">
        {/* Left sidebar */}
        <ResizablePanel defaultSize={leftDefaultSize} minSize={leftMinSize}>
          <div className="h-full overflow-y-auto p-2">
            {left}
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right panel - Vertical split */}
        <ResizablePanel defaultSize={100 - leftDefaultSize} minSize={100 - leftMinSize}>
          <ResizablePanelGroup orientation="vertical" className="h-full">
            {/* Upper right */}
            <ResizablePanel defaultSize={topRightDefaultSize} minSize={topRightMinSize}>
              <div className="h-full overflow-y-auto p-4 bg-muted/30">
                {topRight}
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Lower right - PDF */}
            <ResizablePanel defaultSize={bottomRightDefaultSize} minSize={bottomRightMinSize}>
              <PdfViewer
                ref={pdfViewerRef}
                url={pdfUrl}
                highlights={pdfHighlights}
              />
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
