/* Paper metadata display with resizable PDF viewer on the right.
 * Left side shows title, author, publication year, journal, abstract, and
 * disease-related fields. Right side shows a PDF viewer with zoom/navigation.
 */
import { useState } from 'react'
import { Document, Page } from 'react-pdf'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import type { PaperResp } from '@/api/generated/types.gen'
import { Inheritance, PaperType } from '@/api/generated/types.gen'
import { API_BASE_URL } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { EditableSelectRow, EditableTextRow, SimpleMultiSelectRow } from '@/components/EditableField'
import { EvidencePopover } from '@/components/EvidencePopover'
import { updatePaperPapersPaperIdPatch } from '@/api/generated'

/** Saves on blur with no note dialog -- abstract has no evidence column or
 * `abstract_human_edit_note` field, matching Streamlit's plain `st.text_area`. */
function AbstractField({ value, onSave }: { value: string; onSave: (value: string) => void }) {
  const [draft, setDraft] = useState(value)
  return (
    <Textarea
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft !== value) onSave(draft)
      }}
      rows={8}
      className="text-xs"
    />
  )
}

export function PaperMetadataTab({ paper }: { paper: PaperResp }) {
  const queryClient = useQueryClient()
  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [zoom, setZoom] = useState(100)

  const updateMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      updatePaperPapersPaperIdPatch({
        path: { paper_id: paper.id },
        body,
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers', paper.id] })
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to update paper'
      toast.error(message)
    },
  })

  const save = (body: Record<string, unknown>) => updateMutation.mutate(body)

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
                isSaving={updateMutation.isPending}
                onSave={(value, note) =>
                  save({ title: value || null, title_human_edit_note: note })
                }
              />
              <EditableTextRow
                label="First Author"
                value={paper.first_author || ''}
                isSaving={updateMutation.isPending}
                onSave={(value, note) =>
                  save({ first_author: value || null, first_author_human_edit_note: note })
                }
              />
              <EditableTextRow
                label="Publication Year"
                value={paper.publication_year ? String(paper.publication_year) : ''}
                isSaving={updateMutation.isPending}
                onSave={(value, note) =>
                  save({
                    publication_year: value ? parseInt(value, 10) : null,
                    publication_year_human_edit_note: note,
                  })
                }
              />
              <EditableTextRow
                label="Journal Name"
                value={paper.journal_name || ''}
                isSaving={updateMutation.isPending}
                onSave={(value, note) =>
                  save({ journal_name: value || null, journal_name_human_edit_note: note })
                }
              />
              <SimpleMultiSelectRow
                label="Paper Types"
                value={paper.paper_types ?? []}
                options={Object.values(PaperType)}
                max={2}
                onSave={(value) => save({ paper_types: value })}
              />
            </div>

            {/* Abstract */}
            <div className="space-y-2">
              <h3 className="font-semibold text-sm">Abstract</h3>
              <AbstractField value={paper.abstract ?? ''} onSave={(value) => save({ abstract: value || null })} />
            </div>

            {/* Gene-Disease Information */}
            <div className="space-y-3 border-t pt-3">
              <h3 className="font-semibold text-sm">Gene-Disease Information</h3>
              <EditableTextRow
                label="Disease Name"
                value={paper.disease_name || ''}
                evidence={paper.disease_name_evidence}
                isSaving={updateMutation.isPending}
                onSave={(value, note) =>
                  save({ disease_name: value || null, disease_name_human_edit_note: note })
                }
              />

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
              <EditableSelectRow
                label="Inheritance Mode"
                value={paper.disease_inheritance_mode ?? null}
                options={Object.values(Inheritance)}
                allowNone
                evidence={paper.disease_inheritance_mode_evidence}
                isSaving={updateMutation.isPending}
                onSave={(value, note) =>
                  save({
                    disease_inheritance_mode: value,
                    disease_inheritance_mode_human_edit_note: note,
                  })
                }
              />
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
