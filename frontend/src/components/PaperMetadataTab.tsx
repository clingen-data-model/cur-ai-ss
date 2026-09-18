/* Paper metadata display with resizable PDF viewer on the right.
 * Left side shows title, author, publication year, journal, abstract, and
 * disease-related fields. Right side shows a PDF viewer with zoom/navigation.
 */
import { useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import type { PaperResp } from '@/api/generated/types.gen'
import { API_BASE_URL } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EditableTextRow } from '@/components/EditableField'
import { EvidencePopover } from '@/components/EvidencePopover'
import { pillColorFor } from '@/lib/pillColors'
import { updatePaperPapersPaperIdPatch } from '@/api/generated'

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`

export function PaperMetadataTab({ paper }: { paper: PaperResp }) {
  const queryClient = useQueryClient()
  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [zoom, setZoom] = useState(100)

  const updateMutation = useMutation({
    mutationFn: ({ field, value, note }: { field: string; value: string | null; note: string }) =>
      updatePaperPapersPaperIdPatch({
        path: { paper_id: paper.id },
        body: {
          [field]: value,
          [`${field}_human_edit_note`]: note,
        },
        throwOnError: true,
      }),
    onSuccess: () => {
      toast.success('Paper updated')
      queryClient.invalidateQueries({ queryKey: ['papers', paper.id] })
    },
    onError: () => {
      toast.error('Failed to update paper')
    },
  })

  const onDocumentLoadSuccess = ({ numPages: num }: { numPages: number }) => {
    setNumPages(num)
    setPageNumber(1)
  }

  const goToNextPage = () => {
    if (numPages && pageNumber < numPages) {
      setPageNumber(pageNumber + 1)
    }
  }

  const goToPrevPage = () => {
    if (pageNumber > 1) {
      setPageNumber(pageNumber - 1)
    }
  }

  const handleZoomIn = () => {
    setZoom(Math.min(zoom + 10, 200))
  }

  const handleZoomOut = () => {
    setZoom(Math.max(zoom - 10, 50))
  }

  const handleDownloadPdf = () => {
    const link = document.createElement('a')
    link.href = `${API_BASE_URL}${paper.pdf_url}`
    link.download = paper.filename || 'paper.pdf'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  if (!paper.title) {
    return (
      <p className="text-sm text-muted-foreground">
        {paper.filename} not yet extracted...
      </p>
    )
  }

  return (
    <ResizablePanelGroup orientation="horizontal" className="border rounded">
      {/* Left Panel: Metadata */}
      <ResizablePanel minSize={30} defaultSize={40}>
        <div className="overflow-auto p-4">
          <div className="space-y-4 max-w-2xl">
            {/* Basic Metadata */}
            <div className="space-y-3">
              <h3 className="font-semibold text-sm">Publication Details</h3>
              <EditableTextRow
                label="Title"
                value={paper.title || ''}
                onSave={(value, note) =>
                  updateMutation.mutateAsync({ field: 'title', value: value || null, note })
                }
                isSaving={updateMutation.isPending}
              />
              <EditableTextRow
                label="First Author"
                value={paper.first_author || ''}
                onSave={(value, note) =>
                  updateMutation.mutateAsync({ field: 'first_author', value: value || null, note })
                }
                isSaving={updateMutation.isPending}
              />
              <EditableTextRow
                label="Publication Year"
                value={paper.publication_year ? String(paper.publication_year) : ''}
                onSave={(value, note) =>
                  updateMutation.mutateAsync({
                    field: 'publication_year',
                    value: value ? String(parseInt(value, 10)) : null,
                    note,
                  })
                }
                isSaving={updateMutation.isPending}
              />
              <EditableTextRow
                label="Journal Name"
                value={paper.journal_name || ''}
                onSave={(value, note) =>
                  updateMutation.mutateAsync({ field: 'journal_name', value: value || null, note })
                }
                isSaving={updateMutation.isPending}
              />
              {paper.paper_types && paper.paper_types.length > 0 && (
                <div className="flex items-center justify-between gap-3 py-1.5 border-b">
                  <span className="text-sm text-muted-foreground w-44">Paper Types</span>
                  <div className="flex flex-wrap gap-1 flex-1 justify-end">
                    {paper.paper_types.map((type) => (
                      <Badge key={type} className={pillColorFor(type)} variant="outline">
                        {type}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Abstract */}
            {paper.abstract && (
              <div className="space-y-2">
                <h3 className="font-semibold text-sm">Abstract</h3>
                <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                  {paper.abstract}
                </p>
              </div>
            )}

            {/* Gene-Disease Information */}
            <div className="space-y-3 border-t pt-3">
              <h3 className="font-semibold text-sm">Gene-Disease Information</h3>
              <div className="flex items-center justify-between gap-3 py-1.5 border-b">
                <span className="text-sm text-muted-foreground w-44">Disease Name</span>
                <div className="flex items-center gap-1 flex-1 justify-end">
                  <span className="text-sm">{paper.disease_name || '—'}</span>
                  <EvidencePopover block={paper.disease_name_evidence} />
                </div>
              </div>

              {/* MONDO Disease */}
              <div className="flex items-center justify-between gap-3 py-1.5 border-b">
                <span className="text-sm text-muted-foreground w-44">MONDO Disease</span>
                <div className="flex items-center gap-1 flex-1 justify-end">
                  {paper.mondo.value ? (
                    <span className="text-sm">
                      {paper.mondo.value.mondo_id} — {paper.mondo.value.label}
                    </span>
                  ) : (
                    <span className="text-sm text-muted-foreground">Not linked</span>
                  )}
                  <EvidencePopover block={paper.mondo} />
                </div>
              </div>

              {/* Disease Inheritance Mode */}
              <div className="flex items-center justify-between gap-3 py-1.5 border-b">
                <span className="text-sm text-muted-foreground w-44">
                  Inheritance Mode
                </span>
                <div className="flex items-center gap-1 flex-1 justify-end">
                  <span className="text-sm">
                    {paper.disease_inheritance_mode || '—'}
                  </span>
                  <EvidencePopover block={paper.disease_inheritance_mode_evidence} />
                </div>
              </div>
            </div>

            {/* Metadata Summary */}
            <div className="space-y-2 border-t pt-3 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Patients</span>
                <span>{paper.patient_count}</span>
              </div>
              <div className="flex justify-between">
                <span>Probands</span>
                <span>{paper.proband_count}</span>
              </div>
              <div className="flex justify-between">
                <span>Variants</span>
                <span>{paper.variant_count}</span>
              </div>
              <div className="flex justify-between">
                <span>Occurrences</span>
                <span>{paper.patient_variant_occurrences_count}</span>
              </div>
            </div>
          </div>
        </div>
      </ResizablePanel>

      {/* Resize Handle */}
      <ResizableHandle />

      {/* Right Panel: PDF Viewer */}
      <ResizablePanel minSize={30} defaultSize={60}>
        <div className="h-full flex flex-col bg-muted/30">
          {/* Toolbar */}
          <div className="flex items-center justify-between gap-2 p-3 border-b bg-background">
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={goToPrevPage}
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
                onClick={goToNextPage}
                disabled={!numPages || pageNumber >= numPages}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleZoomOut}
                disabled={zoom <= 50}
              >
                <ZoomOut className="h-4 w-4" />
              </Button>
              <span className="text-xs text-muted-foreground min-w-12 text-center">
                {zoom}%
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleZoomIn}
                disabled={zoom >= 200}
              >
                <ZoomIn className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleDownloadPdf}
                title="Download PDF"
              >
                <Download className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* PDF Container */}
          <div className="flex-1 overflow-auto bg-muted/50 flex items-start justify-center p-4">
            <Document
              file={`${API_BASE_URL}${paper.pdf_url}`}
              onLoadSuccess={onDocumentLoadSuccess}
              loading={<p className="text-xs text-muted-foreground">Loading PDF...</p>}
              error={<p className="text-xs text-red-500">Failed to load PDF</p>}
            >
              <Page
                pageNumber={pageNumber}
                scale={zoom / 100}
                renderTextLayer={false}
                renderAnnotationLayer={false}
              />
            </Document>
          </div>
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
