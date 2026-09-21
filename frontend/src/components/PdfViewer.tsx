/* Renders a PDF with highlight overlays -- used by the evidence "View in PDF"
 * sheet. Coordinates come from the /grobid-annotation endpoint, which is
 * side-effect-free (unlike /highlight, which mutates a shared highlighted.pdf
 * on disk), so this is safe for multiple curators to use concurrently.
 *
 * Same react-pdf setup as PaperMetadataTab.tsx -- see frontend/README.md for
 * why only react-pdf may import pdfjs-dist.
 *
 * No find-in-document here (yet): an attempt at it, and why it was dropped,
 * is in the frontend README's "Known deployment caveats" section.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download, X } from 'lucide-react'
import type { GrobidAnnotation } from '@/api/generated/types.gen'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

// Matches Streamlit's default highlight color (lib/ui/paper/shared.py COLORS[0]).
const HIGHLIGHT_COLOR = '#FFF59D'

// PaperMetadataTab sets this too, at module scope, and eager route imports mean
// it has usually already run. Setting it defensively keeps this component from
// depending on that ordering.
if (!pdfjs.GlobalWorkerOptions.workerSrc) {
  pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`
}

interface PdfViewerProps {
  url: string
  filename?: string | null
  annotations: GrobidAnnotation[]
  onClose?: () => void
}

export function PdfViewer({ url, filename, annotations, onClose }: PdfViewerProps) {
  const firstHighlightRef = useRef<HTMLDivElement | null>(null)

  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [zoom, setZoom] = useState(100)
  const [loadError, setLoadError] = useState<string | null>(null)
  // originalWidth/originalHeight are the unscaled (scale=1) page dimensions
  // -- the same coordinate space GROBID reports annotations in -- so overlay
  // percentages stay correct at any zoom.
  const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null)

  // GROBID numbers the pages it found the evidence on; open on the first.
  const targetPage = useMemo(
    () => (annotations.length > 0 ? Math.min(...annotations.map((a) => a.page)) : null),
    [annotations],
  )

  // Also re-jumps if the curator picks a different quote while the sheet
  // stays open (annotations change, but the sheet/document doesn't remount).
  useEffect(() => {
    if (targetPage !== null) setPageNumber(targetPage)
  }, [targetPage])

  const onDocumentLoadSuccess = useCallback(({ numPages: count }: { numPages: number }) => {
    setNumPages(count)
  }, [])

  const onDocumentLoadError = useCallback((error: Error) => {
    setLoadError(error.message)
  }, [])

  // react-pdf augments the raw pdfjs PDFPageProxy with originalWidth/
  // originalHeight (unscaled); that augmented type isn't part of react-pdf's
  // public export surface, so this is typed structurally instead.
  const onPageLoadSuccess = useCallback((page: { originalWidth: number; originalHeight: number }) => {
    setPageSize({ width: page.originalWidth, height: page.originalHeight })
  }, [])

  const goToPage = (page: number) => {
    if (page < 1 || (numPages && page > numPages)) return
    setPageNumber(page)
  }

  // Bring the evidence on screen once its rects exist, so it's visible even
  // when it sits far down a long page.
  useEffect(() => {
    firstHighlightRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [pageNumber, pageSize, annotations])

  const handleDownloadPdf = () => {
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'paper.pdf'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const pageAnnotations = annotations.filter((a) => a.page === pageNumber)

  return (
    <div className="h-full flex flex-col bg-muted/30">
      <div className="flex items-center justify-between gap-2 p-3 border-b bg-background">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToPage(pageNumber - 1)}
            disabled={pageNumber <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-xs text-muted-foreground min-w-16 text-center">
            {numPages ? `${pageNumber} / ${numPages}` : 'Loading...'}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToPage(pageNumber + 1)}
            disabled={!numPages || pageNumber >= numPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setZoom((z) => Math.max(z - 10, 50))}
            disabled={zoom <= 50}
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-xs text-muted-foreground min-w-12 text-center">{zoom}%</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setZoom((z) => Math.min(z + 10, 200))}
            disabled={zoom >= 200}
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={handleDownloadPdf} title="Download PDF">
            <Download className="h-4 w-4" />
          </Button>
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose} title="Close">
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </Button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-muted/50 flex items-start justify-center p-4">
        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={
            <div className="flex items-center justify-center p-8">
              <Spinner />
            </div>
          }
          error={<p className="text-xs text-red-500 p-8">{loadError ?? 'Failed to load PDF'}</p>}
        >
          <div className="relative inline-block">
            <Page
              pageNumber={pageNumber}
              scale={zoom / 100}
              onLoadSuccess={onPageLoadSuccess}
              renderTextLayer={false}
              renderAnnotationLayer={false}
            />
            {pageSize &&
              pageAnnotations.map((annotation, index) => (
                <div
                  key={`${annotation.page}-${annotation.x}-${annotation.y}-${index}`}
                  ref={index === 0 ? firstHighlightRef : undefined}
                  aria-hidden
                  className="absolute pointer-events-none mix-blend-multiply"
                  style={{
                    backgroundColor: HIGHLIGHT_COLOR,
                    left: `${(annotation.x / pageSize.width) * 100}%`,
                    top: `${(annotation.y / pageSize.height) * 100}%`,
                    width: `${(annotation.width / pageSize.width) * 100}%`,
                    height: `${(annotation.height / pageSize.height) * 100}%`,
                  }}
                />
              ))}
          </div>
        </Document>
      </div>
    </div>
  )
}
