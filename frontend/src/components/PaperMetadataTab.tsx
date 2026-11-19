/* Paper metadata beside the paper. Left: title, author, publication year,
 * journal, PMID, abstract and the disease fields. Right: the shared PDF view
 * (EvidencePanes), in the same split the reviews use (ReviewSplit), so a
 * row's View in PDF highlights its passage beside it rather than opening the
 * page's sheet, and the divider drags. It had its
 * own one-page react-pdf viewer, with no highlights, until 2026-11-19.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import type { PaperResp } from '@/api/generated/types.gen'
import { Inheritance, PaperType } from '@/api/generated/types.gen'
import { Textarea } from '@/components/ui/textarea'
import { EditableSelectRow, EditableTextRow, SimpleMultiSelectRow } from '@/components/EditableField'
import { EvidencePopover } from '@/components/EvidencePopover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { updatePaperPapersPaperIdPatch } from '@/api/generated'
import { EvidencePanes, PdfHighlightProvider, type HighlightTarget } from '@/components/PdfHighlightProvider'
import { ReviewSplit } from '@/components/ReviewParts'

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
  // What a row's View in PDF asked to highlight; nothing until one does.
  const [target, setTarget] = useState<HighlightTarget | null>(null)

  const updateMutation = useMutation({
    mutationKey: ['paper-edit', paper.id],
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

  if (!paper.title) {
    return <p className="text-sm text-muted-foreground">{paper.filename} not yet extracted...</p>
  }

  return (
    <PdfHighlightProvider paperId={paper.id} pdfUrl={paper.pdf_url} filename={paper.filename} inline={setTarget}>
      <div className="flex h-[calc(100vh-14rem)] min-h-[32rem] flex-col rounded border">
        <ReviewSplit
          reviewSize="40%"
          review={
            <div className="min-h-0 flex-1 overflow-auto p-4">
              <div className="space-y-4 max-w-2xl">
                {/* Basic Metadata */}
                <div className="space-y-3">
                  <h3 className="font-semibold text-sm">Publication Details</h3>
                  <EditableTextRow
                    label="Title"
                    value={paper.title || ''}
                    isSaving={updateMutation.isPending}
                    onSave={(value, note) => save({ title: value || null, title_human_edit_note: note })}
                  />
                  <EditableTextRow
                    label="First Author"
                    value={paper.first_author || ''}
                    isSaving={updateMutation.isPending}
                    onSave={(value, note) => save({ first_author: value || null, first_author_human_edit_note: note })}
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
                    onSave={(value, note) => save({ journal_name: value || null, journal_name_human_edit_note: note })}
                  />
                  <EditableTextRow
                    label="PMID"
                    value={paper.pmid || ''}
                    isSaving={updateMutation.isPending}
                    link={{
                      href: `https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(paper.pmid ?? '')}/`,
                      label: 'Open in PubMed',
                    }}
                    onSave={(value, note) => save({ pmid: value.trim() || null, pmid_human_edit_note: note })}
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
                    onSave={(value, note) => save({ disease_name: value || null, disease_name_human_edit_note: note })}
                  />

                  {/* MONDO Disease */}
                  <div className="flex items-center justify-between gap-3 py-1.5 border-b">
                    <span className="text-sm text-muted-foreground w-44">MONDO Disease</span>
                    <div className="flex items-center gap-1 flex-1 justify-end">
                      {paper.mondo.value ? (
                        <Tooltip>
                          <TooltipTrigger render={<span className="text-sm cursor-help" />}>
                            {paper.mondo.value.mondo_id}
                          </TooltipTrigger>
                          <TooltipContent>{paper.mondo.value.label}</TooltipContent>
                        </Tooltip>
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
                    <span>Individuals</span>
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
          }
          pdf={<EvidencePanes paperId={paper.id} pdfUrl={paper.pdf_url} filename={paper.filename} target={target} />}
        />
      </div>
    </PdfHighlightProvider>
  )
}
