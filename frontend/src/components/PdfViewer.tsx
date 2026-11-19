/* Renders a PDF with highlight overlays -- the app's one PDF view, behind
 * EvidencePanes: the evidence "View in PDF" sheet, the occurrence and HPO
 * reviews and the Paper Metadata tab. Coordinates come from `POST /papers/{id}/highlight`, which is
 * read-only (it resolves a block's citations to precomputed boxes and writes
 * nothing on disk), so this is safe for multiple curators to use concurrently.
 *
 * See frontend/README.md for why only react-pdf may import pdfjs-dist.
 *
 * Find-in-document draws its own overlay rects, the same way the evidence
 * highlight above does, rather than injecting markup into react-pdf's text
 * layer (tried first, via the public `customTextRenderer` prop, and dropped:
 * nothing rendered, and text-layer CSS turned out to have a `.textLayer
 * :is(span, br)` rule that yanks any nested span out of the inline flow
 * regardless of depth). Search is two parts: a lightweight per-page text
 * index (built once, on load, from `getTextContent()`) to know which pages
 * contain the query and jump between them, and per-page match rects computed
 * from each matching text item's own position (via
 * `viewport.convertToViewportPoint`, the same scale-1/top-left-origin space
 * the page sizes below are in).
 *
 * The pages are one continuous scroll (since 2026-11-19; it showed one page
 * at a time before). Every page's size and own rotation are read when the
 * document loads, so each page's slot, and the highlights on it, are laid out
 * at once, but a page's canvas is drawn only while it is near the viewport
 * (`PageSlot`), which keeps a long supplement at 200% from holding a canvas
 * per page. The page counter is the page at the top of the view, and the
 * arrows, ← → and find-in-document scroll to a page rather than swap it.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
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
  RotateCw,
  X,
} from 'lucide-react'
import type { GrobidAnnotation } from '@/api/generated/types.gen'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Hint } from '@/components/Hint'

// Matches Streamlit's default highlight color (lib/ui/paper/shared.py COLORS[0]).
const HIGHLIGHT_COLOR = '#FFF59D'
// Distinct from the evidence highlight above, so a curator can tell "this is
// what I searched for" apart from "this is the extracted quote".
const SEARCH_MATCH_COLOR = '#FFB74D'

// The pdf.js worker, from the CDN (frontend/README.md). Set unconditionally:
// react-pdf gives workerSrc a default of its own ('pdf.worker.mjs', which
// does not resolve in the build), so a "set it if unset" guard never fired;
// every PDF view worked only because PaperMetadataTab set it at module scope,
// until that tab moved onto this viewer.
pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`

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
    /** The page's own /Rotate, which pdf.js applies by default. */
    rotate: number
    getTextContent(): Promise<{ items: unknown[] }>
    getViewport(params: { scale: number }): {
      width: number
      height: number
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

interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** A rect in the page's default frame (W x H, /Rotate applied, where the
 * backend's boxes and the text items above live), moved to where it lands
 * after the page is turned a further `turn` degrees clockwise. A quarter
 * turn swaps the frame to H x W. */
function turnRect(rect: Rect, turn: number, page: { width: number; height: number }): Rect {
  const { x, y, width, height } = rect
  switch (turn) {
    case 90:
      return { x: page.height - y - height, y: x, width: height, height: width }
    case 180:
      return { x: page.width - x - width, y: page.height - y - height, width, height }
    case 270:
      return { x: y, y: page.width - x - width, width: height, height: width }
    default:
      return rect
  }
}

/* A curator's turns are kept in the browser per PDF, so a page turned once
 * stays turned on the next visit. Browser storage can be absent or throw
 * (private windows, cleared site data), so both directions are guarded. */
function turnsKey(url: string): string {
  return `pdf-turns:${url}`
}

function readTurns(url: string): Record<number, number> {
  try {
    const raw = localStorage.getItem(turnsKey(url))
    return raw ? (JSON.parse(raw) as Record<number, number>) : {}
  } catch {
    return {}
  }
}

function writeTurns(url: string, turns: Record<number, number>): void {
  try {
    localStorage.setItem(turnsKey(url), JSON.stringify(turns))
  } catch {
    // Nothing to do: the turn still holds for this visit.
  }
}

/** A page's size at scale 1 with its own /Rotate applied (the frame the
 * backend's boxes and the text index are in), and that rotation, which
 * react-pdf's `rotate` must be given whole. */
interface PageMeta {
  width: number
  height: number
  rotate: number
}

/** How far outside the view a page's canvas is still drawn, so scrolling
 * meets pages already painted. */
const RENDER_MARGIN = '150% 0px'
const PAGE_GAP_PX = 16

/** One page's place in the scroll: a box of the page's turned size, holding
 * the canvas while it is near the view and the highlights always (they are
 * positioned in percentages, so they need no canvas to scroll to). */
function PageSlot({
  pageNumber,
  meta,
  turn,
  scale,
  root,
  slotRef,
  children,
}: {
  pageNumber: number
  meta: PageMeta
  turn: number
  scale: number
  root: HTMLElement | null
  slotRef: (element: HTMLDivElement | null) => void
  children: React.ReactNode
}) {
  const [near, setNear] = useState(false)
  const elementRef = useRef<HTMLDivElement | null>(null)
  const frame = turn % 180 ? { width: meta.height, height: meta.width } : meta

  useEffect(() => {
    const element = elementRef.current
    if (!element || !root) return
    const observer = new IntersectionObserver(([entry]) => setNear(entry.isIntersecting), {
      root,
      rootMargin: RENDER_MARGIN,
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [root])

  return (
    <div
      ref={(element) => {
        elementRef.current = element
        slotRef(element)
      }}
      data-page={pageNumber}
      className="relative bg-white shadow-sm"
      style={{ width: frame.width * scale, height: frame.height * scale }}
    >
      {near && (
        <Page
          pageNumber={pageNumber}
          scale={scale}
          rotate={(meta.rotate + turn) % 360}
          renderTextLayer={false}
          renderAnnotationLayer={false}
          loading={null}
        />
      )}
      {children}
    </div>
  )
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
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null)
  const slots = useRef(new Map<number, HTMLDivElement>())

  const [numPages, setNumPages] = useState<number | null>(null)
  // The page at the top of the view, read from the scroll position.
  const [pageNumber, setPageNumber] = useState(1)
  const [zoom, setZoom] = useState(100)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [pageMeta, setPageMeta] = useState<PageMeta[] | null>(null)
  // One entry per page, 0-indexed by page number - 1. Built once when the
  // document loads; used to find which pages match a query and to position
  // the highlight rects on them.
  const [pageItems, setPageItems] = useState<PageTextItem[][] | null>(null)
  const [query, setQuery] = useState('')
  // The curator's quarter turns per page, on top of the page's own /Rotate.
  // A landscape table drawn sideways on a portrait page with no /Rotate (60
  // of dev-caa's 1396 pages on 2026-11-04) reads sideways until turned, and
  // no viewer can tell from the file.
  const [turns, setTurns] = useState<Record<number, number>>(() => readTurns(url))
  useEffect(() => writeTurns(url, turns), [url, turns])

  const scale = zoom / 100

  /** Scroll the view so `element` sits at the top (a page) or the middle (a
   * highlight). Done on the scroller itself, not with scrollIntoView, which
   * would also scroll the page or dialog around the viewer. */
  const scrollTo = useCallback(
    (element: HTMLElement, block: 'start' | 'center') => {
      if (!scroller) return
      const view = scroller.getBoundingClientRect()
      const box = element.getBoundingClientRect()
      const top = box.top - view.top + scroller.scrollTop
      const left = box.left - view.left + scroller.scrollLeft
      scroller.scrollTo({
        top: block === 'start' ? top - PAGE_GAP_PX : top - (view.height - box.height) / 2,
        left: block === 'start' ? scroller.scrollLeft : left - (view.width - box.width) / 2,
      })
    },
    [scroller],
  )

  const goToPage = (page: number) => {
    if (page < 1 || (numPages && page > numPages)) return
    const slot = slots.current.get(page)
    if (slot) scrollTo(slot, 'start')
  }

  const onScroll = () => {
    if (!scroller) return
    // The last page whose top has passed a third of the way down the view.
    const line = scroller.getBoundingClientRect().top + scroller.clientHeight / 3
    let current = 1
    for (const [page, slot] of slots.current) {
      if (slot.getBoundingClientRect().top <= line && page > current) current = page
    }
    setPageNumber(current)
  }

  const onDocumentLoadSuccess = useCallback((document: PdfTextSource) => {
    setNumPages(document.numPages)
    // Sizes first, so the scroll can be laid out; then the text index in the
    // background, search being unavailable (matchCount stays 0) until it is.
    void (async () => {
      const meta: PageMeta[] = []
      for (let i = 1; i <= document.numPages; i++) {
        const page = await document.getPage(i)
        const viewport = page.getViewport({ scale: 1 })
        meta.push({ width: viewport.width, height: viewport.height, rotate: page.rotate })
      }
      setPageMeta(meta)
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

  const turn = turns[pageNumber] ?? 0
  const turnPage = () => setTurns((prev) => ({ ...prev, [pageNumber]: (turn + 90) % 360 }))

  // Where a box in page `page`'s default frame lands on the turned page.
  const place = (page: number, rect: Rect): CSSProperties | undefined => {
    const meta = pageMeta?.[page - 1]
    if (!meta) return undefined
    const pageTurn = turns[page] ?? 0
    const frame = pageTurn % 180 ? { width: meta.height, height: meta.width } : meta
    const turned = turnRect(rect, pageTurn, meta)
    return {
      left: `${(turned.x / frame.width) * 100}%`,
      top: `${(turned.y / frame.height) * 100}%`,
      width: `${(turned.width / frame.width) * 100}%`,
      height: `${(turned.height / frame.height) * 100}%`,
    }
  }

  // GROBID numbers the pages it found the evidence on; the first box on the
  // first of them is brought to the middle of the view whenever the evidence
  // changes (the sheet stays open while the curator picks another quote) or
  // the layout under it does.
  const firstAnnotation = useMemo(() => {
    if (annotations.length === 0) return null
    const page = Math.min(...annotations.map((a) => a.page))
    return annotations.find((a) => a.page === page) ?? null
  }, [annotations])

  useEffect(() => {
    const highlight = firstHighlightRef.current
    if (highlight) scrollTo(highlight, 'center')
    else if (pageMeta) {
      const slot = slots.current.get(pageNumber)
      if (slot) scrollTo(slot, 'start')
    }
    // pageNumber is read, not watched: scrolling must not re-anchor the view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstAnnotation, pageMeta, zoom, turns, scrollTo])

  const normalizedQuery = query.trim().toLowerCase()

  // A match only counts if it's contained within a single text run, so a
  // query spanning two runs (e.g. across a font change or line wrap) won't
  // be found -- an accepted simplification, not a bug to chase.
  const matches = useMemo(() => {
    if (!pageItems || !normalizedQuery) return { pages: [] as number[], total: 0, rects: new Map<number, PageTextItem[]>() }
    const pages: number[] = []
    const rects = new Map<number, PageTextItem[]>()
    let total = 0
    pageItems.forEach((items, index) => {
      const found = items.flatMap((item) => matchRectsInItem(item, normalizedQuery))
      if (found.length > 0) {
        pages.push(index + 1)
        rects.set(index + 1, found)
        total += found.length
      }
    })
    return { pages, total, rects }
  }, [pageItems, normalizedQuery])

  const goToMatchPage = (direction: 1 | -1) => {
    if (matches.pages.length === 0) return
    const next =
      direction === 1
        ? (matches.pages.find((page) => page > pageNumber) ?? matches.pages[0])
        : ([...matches.pages].reverse().find((page) => page < pageNumber) ?? matches.pages[matches.pages.length - 1])
    goToPage(next)
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
          <Hint label="Previous match">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => goToMatchPage(-1)}
              disabled={matches.pages.length === 0}
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
          </Hint>
          <Hint label="Next match">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => goToMatchPage(1)}
              disabled={matches.pages.length === 0}
            >
              <ChevronDown className="h-4 w-4" />
            </Button>
          </Hint>
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
          <Hint label="Rotate this page">
            <Button variant="ghost" size="sm" onClick={turnPage}>
              <RotateCw className="h-4 w-4" />
            </Button>
          </Hint>
          <Hint label="Download PDF">
            <Button variant="ghost" size="sm" onClick={handleDownloadPdf}>
              <Download className="h-4 w-4" />
            </Button>
          </Hint>
          {onClose && (
            <Hint label="Close">
              <Button variant="ghost" size="sm" onClick={onClose}>
                <X className="h-4 w-4" />
                <span className="sr-only">Close</span>
              </Button>
            </Hint>
          )}
        </div>
      </div>

      {/* Focusable, so a click into the PDF takes the arrow keys: ← and →
          go to the previous and next page, ↑ and ↓ scroll. The two page keys
          stop here, so nothing on the page outside that listens for the same
          keys moves as well. */}
      <div
        ref={setScroller}
        tabIndex={0}
        onScroll={onScroll}
        onKeyDown={(event) => {
          if (event.metaKey || event.ctrlKey || event.altKey) return
          if (event.key === 'ArrowRight') goToPage(pageNumber + 1)
          else if (event.key === 'ArrowLeft') goToPage(pageNumber - 1)
          else return
          event.preventDefault()
          event.stopPropagation()
        }}
        className="min-h-0 flex-1 overflow-auto bg-muted/50 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/40"
      >
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
          {pageMeta ? (
            <div className="mx-auto flex w-fit flex-col p-4" style={{ gap: PAGE_GAP_PX }}>
              {pageMeta.map((meta, index) => {
                const page = index + 1
                return (
                  <PageSlot
                    key={page}
                    pageNumber={page}
                    meta={meta}
                    turn={turns[page] ?? 0}
                    scale={scale}
                    root={scroller}
                    slotRef={(element) => {
                      if (element) slots.current.set(page, element)
                      else slots.current.delete(page)
                    }}
                  >
                    {annotations
                      .filter((annotation) => annotation.page === page)
                      .map((annotation, i) => (
                        <div
                          key={`evidence-${annotation.x}-${annotation.y}-${i}`}
                          ref={annotation === firstAnnotation ? firstHighlightRef : undefined}
                          aria-hidden
                          className="absolute pointer-events-none mix-blend-multiply"
                          style={{ backgroundColor: HIGHLIGHT_COLOR, ...place(page, annotation) }}
                        />
                      ))}
                    {(matches.rects.get(page) ?? []).map((item, i) => (
                      <div
                        key={`search-${item.x}-${item.y}-${i}`}
                        aria-hidden
                        className="absolute pointer-events-none mix-blend-multiply"
                        style={{ backgroundColor: SEARCH_MATCH_COLOR, ...place(page, item) }}
                      />
                    ))}
                  </PageSlot>
                )
              })}
            </div>
          ) : (
            <div className="flex items-center justify-center p-8">
              <Spinner />
            </div>
          )}
        </Document>
      </div>
    </div>
  )
}
