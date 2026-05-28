import React, { useRef, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { Collapsible } from '@base-ui/react/collapsible'
import { FolderIcon, FileIcon, ChevronRightIcon } from 'lucide-react'
import { usePaperPatients } from '@/hooks/usePaperPatients'
import type { FamilyNode, PatientResp } from '@/hooks/usePaperPatients'
import { Spinner } from '@/components/ui/spinner'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import { PdfHighlighter, PdfLoader, Highlight as PdfHighlight } from 'react-pdf-highlighter'
import 'react-pdf-highlighter/dist/style.css'
import * as pdfjs from 'pdfjs-dist'
import { grobidAnnotationPapersPaperIdGrobidAnnotationPost } from '@/api/generated'
import type { GrobidAnnotation } from '@/api/generated/types.gen'

const API_URL = import.meta.env.VITE_API_URL as string

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`

interface Highlight {
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

async function annotationsToHighlights(
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

interface FamilyRowProps {
  node: FamilyNode
  selectedPatientId: number | null
  onPatientClick: (patient: PatientResp) => void
}

function FamilyRow({ node, selectedPatientId, onPatientClick }: FamilyRowProps) {
  return (
    <Collapsible.Root defaultOpen={false} className="w-full">
      <Collapsible.Trigger className="flex w-full items-center gap-1 rounded px-2 py-1 text-sm hover:bg-muted cursor-pointer group">
        <ChevronRightIcon className="size-3.5 transition-transform group-data-[state=open]:rotate-90" />
        <FolderIcon className="size-3.5 text-amber-500" />
        <span className="truncate">{node.family.identifier}</span>
        <span className="ml-auto text-xs text-muted-foreground">
          {node.patients.length}
        </span>
      </Collapsible.Trigger>
      <Collapsible.Panel className="pl-5 space-y-1">
        {node.patients.map((patient) => (
          <button
            key={patient.id}
            onClick={() => onPatientClick(patient)}
            className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-sm text-left hover:bg-muted cursor-pointer ${
              selectedPatientId === patient.id ? 'bg-muted font-medium' : ''
            }`}
          >
            <FileIcon className="size-3.5 text-blue-400" />
            <span className="truncate">{patient.identifier}</span>
          </button>
        ))}
      </Collapsible.Panel>
    </Collapsible.Root>
  )
}

interface PdfViewerProps {
  url: string
  highlights: Highlight[]
  scrollToRef: React.MutableRefObject<((h: Highlight) => void) | null>
  onPdfLoaded: (pdf: pdfjs.PDFDocumentProxy) => void
}

function PdfViewer({ url, highlights, scrollToRef, onPdfLoaded }: PdfViewerProps) {
  console.log('PdfViewer render with highlights:', highlights)
  return (
    <PdfLoader url={url} beforeLoad={<Spinner />}>
      {(pdfDocument) => {
        console.log('PdfDocument loaded')
        onPdfLoaded(pdfDocument)
        return (
          <PdfHighlighter
            pdfDocument={pdfDocument}
            scrollRef={(scrollTo) => {
              scrollToRef.current = scrollTo
            }}
            enableAreaSelection={() => false}
            onScrollChange={() => {}}
            highlights={highlights}
            onSelectionFinished={() => null}
            highlightTransform={(highlight) => (
              <PdfHighlight
                isScrolledTo={false}
                position={highlight.position}
                comment={highlight.comment}
              />
            )}
          />
        )
      }}
    </PdfLoader>
  )
}

export function PatientsPage() {
  const params = useParams({ from: '/papers/$paperId/patients' })
  const paperIdNum = parseInt(params.paperId, 10)
  const { paper, familyNodes, isLoading, isError, error } =
    usePaperPatients(paperIdNum)

  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null)
  const [highlights, setHighlights] = useState<Highlight[]>([])
  const pdfDocRef = useRef<pdfjs.PDFDocumentProxy | null>(null)
  const scrollToRef = useRef<((h: Highlight) => void) | null>(null)

  // Auto-scroll to first highlight when highlights change
  React.useEffect(() => {
    if (highlights.length > 0 && scrollToRef.current) {
      console.log('Scrolling to highlight:', highlights[0])
      // Wait for the highlight to be rendered before scrolling
      setTimeout(() => scrollToRef.current?.(highlights[0]), 200)
    }
  }, [highlights])

  const handlePatientClick = async (patient: PatientResp) => {
    setSelectedPatientId(patient.id)
    if (!pdfDocRef.current) return

    const query =
      (patient as any).identifier_evidence?.quote ?? patient.identifier
    if (!query) return

    try {
      const result = await grobidAnnotationPapersPaperIdGrobidAnnotationPost({
        path: { paper_id: paperIdNum },
        body: {
          queries: [query],
          image_ids: [],
          table_ids: [],
          color: '#FFE28F',
        },
      })
      console.log('Grobid result:', result)
      const annotations = (Array.isArray(result.data) ? result.data : result) as GrobidAnnotation[]
      console.log('Annotations:', annotations)
      const newHighlights = await annotationsToHighlights(
        pdfDocRef.current,
        annotations,
        query,
      )
      console.log('New highlights:', newHighlights)
      setHighlights(newHighlights)
    } catch (err) {
      console.error('Failed to highlight patient:', err)
      setHighlights([])
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-red-500">
          Error loading paper: {error?.message ?? 'Unknown error'}
        </div>
      </div>
    )
  }

  const pdfUrl = paper ? `${API_URL}${(paper as any).pdf_url}` : null

  return (
    <div className="h-[calc(100vh-8rem)] p-4">
      <ResizablePanelGroup orientation="horizontal" className="h-full rounded-lg border">
        {/* Left sidebar - Families & Patients */}
        <ResizablePanel defaultSize={33} minSize={20}>
          <div className="h-full overflow-y-auto p-2">
            <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Families &amp; Patients
            </div>
            {familyNodes.length === 0 ? (
              <div className="px-2 text-sm text-muted-foreground">
                No families found.
              </div>
            ) : (
              familyNodes.map((node) => (
                <FamilyRow
                  key={node.family.id}
                  node={node}
                  selectedPatientId={selectedPatientId}
                  onPatientClick={handlePatientClick}
                />
              ))
            )}
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right panel - PDF Viewer */}
        <ResizablePanel defaultSize={67} minSize={30}>
          <div className="h-full w-full" style={{ position: 'relative' }}>
            {pdfUrl ? (
              <div style={{ position: 'absolute', inset: 0, overflow: 'auto' }}>
                <PdfViewer
                  url={pdfUrl}
                  highlights={highlights}
                  scrollToRef={scrollToRef}
                  onPdfLoaded={(pdf) => {
                    pdfDocRef.current = pdf
                  }}
                />
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
                No PDF available.
              </div>
            )}
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
