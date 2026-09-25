/* Extraction page: the SPA's per-paper review surface, tabbed like the
 * Streamlit paper page (lib/ui/paper/header.py). "Occurrences" is the main
 * tab -- one row per patient/variant link, editable inline, with click-to-
 * expand Patient/Variant detail panels. The other three tabs surface what
 * didn't make it into an occurrence: patients/variants extraction found but
 * linking never connected, and the pedigree image/description.
 */
import { useMemo, useState } from 'react'
import { useParams, Link } from '@tanstack/react-router'
import type { ColumnDef, ExpandedState } from '@tanstack/react-table'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronDown, ChevronRight, FileText } from 'lucide-react'
import { usePaperOccurrences } from '@/hooks/usePaperOccurrences'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { deleteOccurrencePapersPaperIdOccurrencesOccurrenceIdDelete } from '@/api/generated'
import { DataTable } from '@/components/ui/data-table'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { API_BASE_URL, getAccessToken } from '@/lib/api'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import {
  EditableDeNovoCell,
  EditableDiseaseNameCell,
  EditableInheritanceCell,
  EditableTestingMethodsCell,
  EditableZygosityCell,
  MondoDiseaseCell,
} from '@/components/OccurrenceEditableCells'
import { ConfidenceBadge } from '@/components/ConfidenceBadge'
import { EvidencePopover } from '@/components/EvidencePopover'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { pillColorFor } from '@/lib/pillColors'
import { PairOccurrenceDialog } from '@/components/PairOccurrenceDialog'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'
import { PatientHoverCardContent } from '@/components/PatientHoverCard'
import { VariantHoverCardContent } from '@/components/VariantHoverCard'
import { UnassociatedPatientsTab } from '@/components/UnassociatedPatientsTab'
import { UnassociatedVariantsTab } from '@/components/UnassociatedVariantsTab'
import { PipelineGate } from '@/components/PipelineGate'
import { DeleteIconButton } from '@/components/DeleteIconButton'
import { RestoreSnapshotButton } from '@/components/RestoreSnapshotButton'
import { PaperProgressPopover } from '@/components/PaperProgressPopover'
import { ReviewStatusCell } from '@/components/ReviewStatusCell'
import { StatusBadge } from '@/components/StatusBadge'
import { computeStatus } from '@/components/TaskDAG'
import { apiErrorMessage } from '@/lib/apiError'
import { AffectedStatus, ProbandStatus, TaskType } from '@/api/generated/types.gen'
import { PedigreeTab } from '@/components/PedigreeTab'
import { PaperMetadataTab } from '@/components/PaperMetadataTab'
import { PdfHighlightProvider } from '@/components/PdfHighlightProvider'

type ExpandedView = 'patient' | 'variant'

/** Affected status as a dot next to the patient name, rather than its own
 * column -- three states (Affected/Unaffected/Unknown) read fine as a color
 * with a tooltip, and freeing the column keeps the table narrower. */
const AFFECTED_DOT: Record<AffectedStatus, string> = {
  [AffectedStatus.AFFECTED]: 'bg-rose-500',
  [AffectedStatus.UNAFFECTED]: 'bg-muted-foreground/25',
  [AffectedStatus.UNKNOWN]: 'border border-muted-foreground/40',
}

/** Patient/Variant cell: click expands the row's detail panel, hover previews
 * a snippet of it (demographics / ClinVar+gnomAD) without expanding. */
function EntityLink({
  onClick,
  hoverContent,
  children,
}: {
  onClick: () => void
  hoverContent: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <HoverCard>
      <HoverCardTrigger
        render={<button type="button" />}
        onClick={(e) => {
          e.stopPropagation()
          onClick()
        }}
        className="text-left hover:underline underline-offset-2 cursor-pointer"
      >
        {children}
      </HoverCardTrigger>
      <HoverCardContent className="w-72">{hoverContent}</HoverCardContent>
    </HoverCard>
  )
}

function OccurrencesTab({ paperId, rows }: { paperId: number; rows: OccurrenceRow[] }) {
  const queryClient = useQueryClient()
  const [expandedCell, setExpandedCell] = useState<{ rowId: string; view: ExpandedView } | null>(null)

  const toggleExpanded = (rowId: string, view: ExpandedView) => {
    setExpandedCell((prev) => (prev?.rowId === rowId && prev.view === view ? null : { rowId, view }))
  }

  const deleteMutation = useMutation({
    mutationFn: (occurrenceId: number) =>
      deleteOccurrencePapersPaperIdOccurrencesOccurrenceIdDelete({
        path: { paper_id: paperId, occurrence_id: occurrenceId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['occurrences', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Occurrence deleted')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to delete occurrence')),
  })

  const expanded: ExpandedState = expandedCell ? { [expandedCell.rowId]: true } : {}

  const hasPairedVariants = useMemo(() => rows.some((r) => r.pairedVariant), [rows])

  const columns: ColumnDef<OccurrenceRow>[] = useMemo(() => {
    const cols: ColumnDef<OccurrenceRow>[] = [
      {
        id: 'expander',
        size: 40,
        enableSorting: false,
        header: () => null,
        cell: ({ row }) => (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              const rowId = String(row.original.occurrence.id)
              const isExpanded = expandedCell?.rowId === rowId
              if (isExpanded) {
                setExpandedCell(null)
              } else {
                setExpandedCell({ rowId, view: 'patient' })
              }
            }}
            className="cursor-pointer flex items-center"
          >
            {expandedCell?.rowId === String(row.original.occurrence.id) ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </button>
        ),
      },
      {
        id: 'patient',
        header: 'Patient',
        accessorFn: (row) => row.patient.identifier,
        cell: ({ row }) => {
          const { patient } = row.original
          return (
            <div className="flex items-center gap-1.5">
              <Tooltip>
                <TooltipTrigger
                  render={
                    <span className={`size-2.5 rounded-full shrink-0 ${AFFECTED_DOT[patient.affected_status]}`} />
                  }
                />
                <TooltipContent>{patient.affected_status}</TooltipContent>
              </Tooltip>
              <EntityLink
                onClick={() => toggleExpanded(String(row.original.occurrence.id), 'patient')}
                hoverContent={<PatientHoverCardContent paperId={paperId} patient={patient} />}
              >
                {patient.identifier}
              </EntityLink>
              {patient.proband_status === ProbandStatus.PROBAND && (
                <Tooltip>
                  <TooltipTrigger render={<span className="text-muted-foreground cursor-help" />}>*</TooltipTrigger>
                  <TooltipContent>Proband</TooltipContent>
                </Tooltip>
              )}
            </div>
          )
        },
      },
      {
        id: 'variant',
        header: 'Variant',
        accessorFn: (row) => row.variant.variant_description,
        cell: ({ row }) => (
          <EntityLink
            onClick={() => toggleExpanded(String(row.original.occurrence.id), 'variant')}
            hoverContent={<VariantHoverCardContent variant={row.original.variant} />}
          >
            {row.original.variant.variant_description}
          </EntityLink>
        ),
      },
      {
        id: 'variant_type',
        header: 'Variant Type',
        accessorFn: (row) => row.variant.variant_type,
        cell: ({ row }) => (
          <Badge className={pillColorFor(row.original.variant.variant_type)} variant="outline">
            {row.original.variant.variant_type}
          </Badge>
        ),
      },
    ]

    if (hasPairedVariants) {
      cols.push({
        id: 'paired_variant',
        header: 'Paired Variant',
        accessorFn: (row) => row.pairedVariant?.variant_description ?? '',
        cell: ({ row }) => {
          const occurrence = row.original.occurrence
          return (
            <div className="flex items-center gap-1">
              <span>{row.original.pairedVariant?.variant_description ?? '—'}</span>
              {occurrence.paired_variant_confidence && (
                <ConfidenceBadge confidence={occurrence.paired_variant_confidence} />
              )}
              <EvidencePopover block={occurrence.paired_variant_confidence_reasoning} />
            </div>
          )
        },
      })
    }

    cols.push(
      {
        id: 'zygosity',
        header: 'Zygosity',
        cell: ({ row }) => <EditableZygosityCell paperId={paperId} occurrence={row.original.occurrence} />,
      },
      {
        id: 'inheritance',
        header: 'Inheritance',
        cell: ({ row }) => <EditableInheritanceCell paperId={paperId} occurrence={row.original.occurrence} />,
      },
      {
        id: 'de_novo',
        header: 'De Novo',
        cell: ({ row }) => <EditableDeNovoCell paperId={paperId} occurrence={row.original.occurrence} />,
      },
      {
        id: 'testing_methods',
        header: 'Testing Methods',
        cell: ({ row }) => (
          <EditableTestingMethodsCell paperId={paperId} occurrence={row.original.occurrence} />
        ),
      },
    )

    cols.push({
      id: 'disease_name',
      header: 'Disease Name',
      cell: ({ row }) => (
        <EditableDiseaseNameCell paperId={paperId} occurrence={row.original.occurrence} />
      ),
    })

    cols.push({
      id: 'mondo',
      header: 'MONDO Disease',
      cell: ({ row }) => <MondoDiseaseCell occurrence={row.original.occurrence} />,
    })

    cols.push({
      id: 'actions',
      header: '',
      size: 64,
      enableSorting: false,
      cell: ({ row }) => {
        const occurrence = row.original.occurrence
        const siblingOccurrences = rows.filter(
          (r) =>
            r.occurrence.patient_id === occurrence.patient_id &&
            r.occurrence.id !== occurrence.id,
        )
        return (
          <div className="flex items-center gap-0.5">
            <PairOccurrenceDialog
              paperId={paperId}
              occurrence={occurrence}
              siblingOccurrences={siblingOccurrences}
            />
            <DeleteIconButton
              title="Delete occurrence?"
              description="This will permanently delete this patient/variant link. This cannot be undone."
              onDelete={() => deleteMutation.mutate(occurrence.id)}
            />
          </div>
        )
      },
    })

    return cols
  }, [rows, hasPairedVariants, paperId, expandedCell?.rowId, deleteMutation])

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Linking ran but connected no patient to a variant.
      </p>
    )
  }

  return (
    <>
      <p className="text-sm text-muted-foreground mb-2">{rows.length} total occurrences</p>
      <DataTable
        columns={columns}
        data={rows}
        filterPlaceholder="Filter occurrences..."
        getRowId={(row) => String(row.occurrence.id)}
        getRowCanExpand={() => true}
        expandOnRowClick={false}
        expanded={expanded}
        onExpandedChange={() => {}}
        renderSubComponent={({ row }) =>
          expandedCell?.view === 'patient' ? (
            <PatientDetailPanel paperId={paperId} patient={row.patient} />
          ) : (
            <VariantDetailPanel paperId={paperId} variant={row.variant} />
          )
        }
      />
    </>
  )
}

export function ExtractionPage() {
  const params = useParams({ from: '/papers/$paperId/extraction' })
  const paperId = parseInt(params.paperId, 10)
  const { paper, rows, unassociatedPatients, unassociatedVariants, isLoading, isError, error } =
    usePaperOccurrences(paperId)
  const tasks = paper?.tasks ?? []
  const paperStatus = computeStatus(tasks)
  const [isExporting, setIsExporting] = useState(false)

  const handleExportPptx = async () => {
    setIsExporting(true)
    try {
      const token = getAccessToken()
      const headers: HeadersInit = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(`${API_BASE_URL}/papers/${paperId}/curation-export`, {
        headers,
      })
      if (!response.ok) throw new Error(`Failed to export PPTX: ${response.status}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `curation_${paperId}.pptx`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Error exporting PPTX:', err)
    } finally {
      setIsExporting(false)
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

  return (
    <PdfHighlightProvider
      paperId={paperId}
      pdfUrl={paper?.pdf_url}
      filename={paper?.filename}
    >
      <div className="space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <Link to="/" className="text-sm text-muted-foreground hover:underline">
              &larr; All Papers
            </Link>
            <h1 className="text-xl font-semibold mt-1">{paper?.title ?? paper?.filename}</h1>
          </div>
          <div className="flex items-center gap-2">
            {/* Stacked in place of a standalone Re-run Agents button --
                PaperProgressPopover's own refresh icon already opens the
                same RerunTaskDialog, so a second control here was redundant. */}
            {paper && (
              <div className="flex items-center gap-2">
                <PaperProgressPopover
                  paper={{ id: paper.id, title: paper.title, filename: paper.filename, status: paperStatus }}
                >
                  <StatusBadge status={paperStatus} />
                </PaperProgressPopover>
                <ReviewStatusCell paper={paper} />
              </div>
            )}
            {paper && <RestoreSnapshotButton paper={paper} />}
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportPptx}
              disabled={!paper || isExporting}
              title="Export curation summary as PPTX"
            >
              <FileText className="h-4 w-4 mr-2" />
              {isExporting ? 'Exporting...' : 'PPTX'}
            </Button>
          </div>
        </div>

        <Tabs defaultValue="occurrences">
          <TabsList>
            <TabsTrigger value="occurrences">Occurrences</TabsTrigger>
            <TabsTrigger value="unassociated-patients">
              Unassociated Patients
              {unassociatedPatients.length > 0 && (
                <span className="ml-1 text-xs text-muted-foreground">({unassociatedPatients.length})</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="unassociated-variants">
              Unassociated Variants
              {unassociatedVariants.length > 0 && (
                <span className="ml-1 text-xs text-muted-foreground">({unassociatedVariants.length})</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="pedigree">Pedigree Image &amp; Description</TabsTrigger>
            <TabsTrigger value="paper-metadata">Paper Metadata</TabsTrigger>
          </TabsList>

          <TabsContent value="occurrences" className="pt-3">
            <PipelineGate
              tasks={tasks}
              task={TaskType.PATIENT_VARIANT_OCCURRENCES}
              label="Patient/variant linking"
            >
              <OccurrencesTab paperId={paperId} rows={rows} />
            </PipelineGate>
          </TabsContent>
          <TabsContent value="unassociated-patients" className="pt-3">
            <UnassociatedPatientsTab
              paperId={paperId}
              patients={unassociatedPatients}
              tasks={tasks}
            />
          </TabsContent>
          <TabsContent value="unassociated-variants" className="pt-3">
            <UnassociatedVariantsTab
              paperId={paperId}
              variants={unassociatedVariants}
              tasks={tasks}
            />
          </TabsContent>
          <TabsContent value="pedigree" className="pt-3">
            <PedigreeTab paperId={paperId} />
          </TabsContent>
          <TabsContent value="paper-metadata" className="pt-3 h-[70vh]">
            {paper && <PaperMetadataTab paper={paper} />}
          </TabsContent>
        </Tabs>
      </div>
    </PdfHighlightProvider>
  )
}
