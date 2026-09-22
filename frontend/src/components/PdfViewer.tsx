/* Renders a PDF with highlight overlays -- used by the evidence "View in PDF"
 * sheet. Coordinates come from the /grobid-annotation endpoint, which is
 * side-effect-free (unlike /highlight, which mutates a shared highlighted.pdf
 * on disk), so this is safe for multiple curators to use concurrently.
 *
 * Same react-pdf setup as PaperMetadataTab.tsx -- see frontend/README.md for
 * why only react-pdf may import pdfjs-dist.
 *
 * Find-in-document draws its own overlay rects, the same way the evidence
 * highlight above does, rather than injecting markup into react-pdf's text
 * layer (tried first, via the public `customTextRenderer` prop, and dropped:
 * nothing rendered, and text-layer CSS turned out to have a `.textLayer
 * :is(span, br)` rule that yanks any nested span out of the inline flow
 * regardless of depth). It only highlights matches on the page currently on
 * screen (react-pdf renders one page's text layer at a time -- and this
 * component doesn't even use the text layer), so search is two parts: a
 * lightweight per-page text index (built once, on load, from
 * `getTextContent()`) to know which pages contain the query and jump
 * between them, and per-page match rects computed from each matching text
 * item's own position (via `viewport.convertToViewportPoint`, the same
 * scale-1/top-left-origin space `originalWidth`/`originalHeight` are in) to
 * paint once that page is showing.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import {
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  Search,
  ZoomIn,
  ZoomOut,
  Download,
  X,
} from 'lucide-react'
import type { GrobidAnnotation } from '@/api/generated/types.gen'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

// Matches Streamlit's default highlight color (lib/ui/paper/shared.py COLORS[0]).
const HIGHLIGHT_COLOR = '#FFF59D'
// Distinct from the evidence highlight above, so a curator can tell "this is
// what I searched for" apart from "this is the extracted quote".
const SEARCH_MATCH_COLOR = '#FFB74D'

// PaperMetadataTab sets this too, at module scope, and eager route imports mean
// it has usually already run. Setting it defensively keeps this component from
// depending on that ordering.
if (!pdfjs.GlobalWorkerOptions.workerSrc) {
  pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`
}

/** One text run from `getTextContent()`, positioned in the same scale-1,
 * top-left-origin space as `originalWidth`/`originalHeight` -- i.e. the same
 * space GROBID's annotations are already in, so it can reuse the exact same
 * overlay rendering as the evidence highlight. */
interface PageTextItem {
  str: string
  x: number
  y: number
  width: number
  height: number
}

/** Just enough of PDFDocumentProxy/PDFPageProxy/PageViewport to build the
 * index above -- typed structurally so this file never needs to import from
 * pdfjs-dist. */
interface PdfTextSource {
  numPages: number
  getPage(pageNumber: number): Promise<{
    getTextContent(): Promise<{ items: unknown[] }>
    getViewport(params: { scale: number }): {
      convertToViewportPoint(x: number, y: number): number[]
    }
  }>
}

/** `getTextContent()`'s items are really `(TextItem | TextMarkedContent)[]`;
 * only TextItem has `str`/`transform`/`width`/`height`, so this reads them
 * defensively rather than widening PdfTextSource's type to match. */
function parseTextItem(item: unknown): { str: string; transform: number[]; width: number; height: number } | null {
  if (typeof item !== 'object' || item === null) return null
  const { str, transform, width, height } = item as Record<string, unknown>
  if (typeof str !== 'string' || !str.trim()) return null
  if (!Array.isArray(transform) || transform.length !== 6) return null
  if (typeof width !== 'number' || typeof height !== 'number') return null
  return { str, transform, width, height }
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0
  let count = 0
  let position = 0
  for (;;) {
    const index = haystack.indexOf(needle, position)
    if (index === -1) return count
    count += 1
    position = index + needle.length
  }
}

/** A text item from `getTextContent()` is often a whole line (PDF producers
 * commonly emit one string per line, not one per word), so highlighting the
 * item's full box -- as a first pass here did -- covers far more than the
 * match. This carves out one rect per occurrence instead, splitting the
 * item's width proportionally by character offset. Characters aren't
 * uniform width, so it's an approximation, but a much tighter one. */
function matchRectsInItem(item: PageTextItem, query: string): PageTextItem[] {
  const length = item.str.length
  if (length === 0) return []
  const lower = item.str.toLowerCase()
  const rects: PageTextItem[] = []
  let position = 0
  for (;;) {
    const index = lower.indexOf(query, position)
    if (index === -1) return rects
    const end = index + query.length
    rects.push({
      str: item.str.slice(index, end),
      x: item.x + (index / length) * item.width,
      y: item.y,
      width: ((end - index) / length) * item.width,
      height: item.height,
    })
    position = end
  }
}

interface PdfViewerProps {
  url: string
  filename?: string | null
  annotations: GrobidAnnotation[]
  onClose?: () => void
}

export function PdfViewer({ url, filename, annotations, onClose }: PdfViewerProps) {
  const firstHighlightRef = useRef<HTMLDivElement | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)

  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [zoom, setZoom] = useState(100)
  const [loadError, setLoadError] = useState<string | null>(null)
  // originalWidth/originalHeight are the unscaled (scale=1) page dimensions
  // -- the same coordinate space GROBID reports annotations in -- so overlay
  // percentages stay correct at any zoom.
  const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null)
  // One entry per page, 0-indexed by page number - 1. Built once when the
  // document loads; used to find which pages match a query and to position
  // the highlight rects on whichever page is showing.
  const [pageItems, setPageItems] = useState<PageTextItem[][] | null>(null)
  const [query, setQuery] = useState('')

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

  const onDocumentLoadSuccess = useCallback((document: PdfTextSource) => {
    setNumPages(document.numPages)
    // Runs in the background; page rendering doesn't wait on it, and search
    // is simply unavailable (matchCount stays 0) until it resolves.
    void (async () => {
      const pages: PageTextItem[][] = []
      for (let i = 1; i <= document.numPages; i++) {
        const page = await document.getPage(i)
        const viewport = page.getViewport({ scale: 1 })
        const content = await page.getTextContent()
        const items: PageTextItem[] = []
        for (const raw of content.items) {
          const item = parseTextItem(raw)
          if (!item) continue
          // transform[4]/[5] is the item's PDF-space origin; width/height
          // extend from there. Map both corners through the viewport (which
          // handles page rotation/y-flip) and take the bounding box.
          const [x1, y1] = viewport.convertToViewportPoint(item.transform[4] ?? 0, item.transform[5] ?? 0)
          const [x2, y2] = viewport.convertToViewportPoint(
            (item.transform[4] ?? 0) + item.width,
            (item.transform[5] ?? 0) + item.height,
          )
          items.push({
            str: item.str,
            x: Math.min(x1, x2),
            y: Math.min(y1, y2),
            width: Math.abs(x2 - x1),
            height: Math.abs(y2 - y1),
          })
        }
        pages.push(items)
      }
      setPageItems(pages)
    })()
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

  const normalizedQuery = query.trim().toLowerCase()

  // A match only counts if it's contained within a single text run, so a
  // query spanning two runs (e.g. across a font change or line wrap) won't
  // be found -- an accepted simplification, not a bug to chase.
  const matches = useMemo(() => {
    if (!pageItems || !normalizedQuery) return { pages: [] as number[], total: 0 }
    const pages: number[] = []
    let total = 0
    pageItems.forEach((items, index) => {
      const count = items.reduce(
        (sum, item) => sum + countOccurrences(item.str.toLowerCase(), normalizedQuery),
        0,
      )
      if (count > 0) {
        pages.push(index + 1)
        total += count
      }
    })
    return { pages, total }
  }, [pageItems, normalizedQuery])

  const goToMatchPage = (direction: 1 | -1) => {
    if (matches.pages.length === 0) return
    const currentIndex = matches.pages.indexOf(pageNumber)
    const nextIndex =
      currentIndex === -1
        ? 0
        : (currentIndex + direction + matches.pages.length) % matches.pages.length
    setPageNumber(matches.pages[nextIndex])
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'f') {
        event.preventDefault()
        searchInputRef.current?.focus()
        searchInputRef.current?.select()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  const handleDownloadPdf = () => {
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'paper.pdf'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const pageAnnotations = annotations.filter((a) => a.page === pageNumber)
  const currentPageMatches = normalizedQuery
    ? (pageItems?.[pageNumber - 1] ?? []).flatMap((item) => matchRectsInItem(item, normalizedQuery))
    : []

  return (
    <div className="h-full flex flex-col bg-muted/30">
      <div className="flex items-center gap-2 p-3 border-b bg-background">
        <div className="flex shrink-0 items-center gap-1">
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

        <div className="relative flex min-w-0 flex-1 items-center">
          <Search className="pointer-events-none absolute left-2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            ref={searchInputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                goToMatchPage(event.shiftKey ? -1 : 1)
              } else if (event.key === 'Escape' && query !== '') {
                event.preventDefault()
                event.stopPropagation()
                setQuery('')
              }
            }}
            placeholder={pageItems ? 'Find in document' : 'Find in document (loading...)'}
            disabled={!pageItems}
            className="h-8 pl-7 pr-16 text-xs"
          />
          {normalizedQuery !== '' && (
            <span className="pointer-events-none absolute right-2 text-[11px] tabular-nums text-muted-foreground">
              {matches.total === 0 ? '0' : `${matches.total} on ${matches.pages.length} pg`}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToMatchPage(-1)}
            disabled={matches.pages.length === 0}
            title="Previous match"
          >
            <ChevronUp className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToMatchPage(1)}
            disabled={matches.pages.length === 0}
            title="Next match"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex shrink-0 items-center gap-1">
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
                  key={`evidence-${annotation.page}-${annotation.x}-${annotation.y}-${index}`}
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
            {pageSize &&
              currentPageMatches.map((item, index) => (
                <div
                  key={`search-${pageNumber}-${item.x}-${item.y}-${index}`}
                  aria-hidden
                  className="absolute pointer-events-none mix-blend-multiply"
                  style={{
                    backgroundColor: SEARCH_MATCH_COLOR,
                    left: `${(item.x / pageSize.width) * 100}%`,
                    top: `${(item.y / pageSize.height) * 100}%`,
                    width: `${(item.width / pageSize.width) * 100}%`,
                    height: `${(item.height / pageSize.height) * 100}%`,
                  }}
                />
              ))}
          </div>
        </Document>
      </div>
    </div>
  )
}
