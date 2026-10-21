/* Extraction page: the SPA's per-paper review surface, tabbed like the
 * Streamlit paper page (lib/ui/paper/header.py). "Occurrences" is the main
 * tab -- one row per patient/variant link, editable inline, with click-to-
 * expand Patient/Variant detail panels. The other three tabs surface what
 * didn't make it into an occurrence: patients/variants extraction found but
 * linking never connected, and the described figures (pedigree and
 * genotyping images).
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearch, Link } from '@tanstack/react-router'
import type { ColumnDef, ExpandedState } from '@tanstack/react-table'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FileText } from 'lucide-react'
import { usePaperOccurrences } from '@/hooks/usePaperOccurrences'
import { usePaperFlags } from '@/hooks/usePaperFlags'
import type { FlagIndex } from '@/hooks/usePaperFlags'
import { FlagIndicator } from '@/components/FlagIndicator'
import { FlagsTab } from '@/components/FlagsTab'
import type { FlagTarget } from '@/lib/flagTarget'
import { DEFAULT_EXTRACTION_TAB, isExtractionTab, type ExtractionTab } from '@/lib/extractionTabs'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { deleteOccurrencePapersPaperIdOccurrencesOccurrenceIdDelete } from '@/api/generated'
import { DataTable } from '@/components/ui/data-table'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { API_BASE_URL, getAccessToken } from '@/lib/api'
import {
  EditableDeNovoCell,
  EditableDiseaseNameCell,
  EditableInheritanceCell,
  EditableTestingMethodsCell,
  EditableVariantTypeCell,
  EditableZygosityCell,
  MondoDiseaseCell,
} from '@/components/OccurrenceEditableCells'
import { EvidencePopover } from '@/components/EvidencePopover'
import { ManuallyCreatedIndicator } from '@/components/ManuallyCreatedIndicator'
import { PairOccurrenceDialog } from '@/components/PairOccurrenceDialog'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'
import { displayProteinChange } from '@/lib/hgvs'
import { EntityLink } from '@/components/EntityLink'
import { PatientIdCell } from '@/components/PatientIdCell'
import { RowExpander } from '@/components/RowExpander'
import { VariantHoverCardContent } from '@/components/VariantHoverCard'
import { UnassociatedPatientsTab } from '@/components/UnassociatedPatientsTab'
import { UnassociatedVariantsTab } from '@/components/UnassociatedVariantsTab'
import { PipelineGate } from '@/components/PipelineGate'
import { DeleteIconButton } from '@/components/DeleteIconButton'
import { RestoreSnapshotButton } from '@/components/RestoreSnapshotButton'
import { PaperProgressPopover } from '@/components/PaperProgressPopover'
import { ReviewStatusCell } from '@/components/ReviewStatusCell'
import { StatusBadge } from '@/components/StatusBadge'
import { computeStatus } from '@/lib/taskState'
import { apiErrorMessage } from '@/lib/apiError'
import { ProbandStatus, TaskType } from '@/api/generated/types.gen'
import { Switch } from '@/components/ui/switch'
import { FiguresTab } from '@/components/FiguresTab'
import { FamiliesTab } from '@/components/FamiliesTab'
import { PaperMetadataTab } from '@/components/PaperMetadataTab'
import { PdfHighlightProvider } from '@/components/PdfHighlightProvider'

type ExpandedView = 'patient' | 'variant'

/** Same "any of patient/variant/occurrence was curator-created" check as
 * ManuallyCreatedIndicator, reused to tint the whole row -- the icon alone
 * sits in a narrow, unlabeled column that's easy to miss. */
function isManuallyCreatedRow(row: OccurrenceRow): boolean {
  return (
    row.patient.created_by_user_id != null ||
    row.variant.created_by_user_id != null ||
    row.occurrence.created_by_user_id != null
  )
}

/** "c.123A>G (p.Arg41Gly)" -- the protein change alongside the genomic/cDNA
 * description, when known. Omitted when they're the same string:
 * variant_description falls back to hgvs_p itself when no genomic/cDNA
 * notation exists (see get_variant_description in lib/models/variant.py),
 * which would otherwise show "p.Arg41Gly (p.Arg41Gly)". A predicted change
 * "p.(Arg41Gly)" loses its own parentheses (displayProteinChange) so the label
 * does not read "(p.(Arg41Gly))". */
function VariantLabel({ description, hgvsP }: { description: string; hgvsP: string | null }) {
  return (
    <>
      {description}
      {hgvsP && hgvsP !== description && (
        <span className="text-muted-foreground"> ({displayProteinChange(hgvsP)})</span>
      )}
    </>
  )
}

/** Every flag that touches an occurrence row: the occurrence's own, plus
 * the patient's and the variant's, since this tab is where both are read. */
function rowFlags(flags: FlagIndex, row: OccurrenceRow) {
  const seen = new Set<number>()
  return [
    ...(flags.byOccurrence.get(row.occurrence.id) ?? []),
    ...(flags.byPatient.get(row.patient.id) ?? []),
    ...(flags.byVariant.get(row.variant.id) ?? []),
  ].filter((flag) => !seen.has(flag.id) && seen.add(flag.id))
}

function isProbandRow(row: OccurrenceRow): boolean {
  return row.patient.proband_status === ProbandStatus.PROBAND
}

function OccurrencesTab({
  paperId,
  rows,
  flags,
  focus,
}: {
  paperId: number
  rows: OccurrenceRow[]
  flags: FlagIndex
  /** An occurrence to open on arrival (from a flag's About chip), on the
   * panel the chip names. A new object is a new request, so the same row can
   * be asked for again after the reader has closed it. */
  focus?: Extract<FlagTarget, { kind: 'occurrence' }> | null
}) {
  const queryClient = useQueryClient()
  const [expandedCell, setExpandedCell] = useState<{ rowId: string; view: ExpandedView } | null>(
    focus ? { rowId: String(focus.id), view: focus.view ?? 'patient' } : null,
  )
  // Proband-only view: the probands' rows alone, the relatives hidden. Plain
  // page state like the table's search box, and lifted the same way the
  // search is when a flag chip names a relative's row, rather than scrolling
  // to a row that is not there.
  const [probandOnly, setProbandOnly] = useState(false)
  useEffect(() => {
    if (!focus) return
    setExpandedCell({ rowId: String(focus.id), view: focus.view ?? 'patient' })
    const target = rows.find((r) => r.occurrence.id === focus.id)
    if (target && !isProbandRow(target)) setProbandOnly(false)
    // rows is read, not watched: a data refresh must not re-open the row.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus])
  const reveal = useMemo(() => (focus ? { rowId: String(focus.id) } : null), [focus])
  const probandCount = useMemo(() => rows.filter(isProbandRow).length, [rows])
  const visibleRows = useMemo(() => (probandOnly ? rows.filter(isProbandRow) : rows), [rows, probandOnly])

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
        id: 'created',
        header: '',
        size: 28,
        enableSorting: false,
        cell: ({ row }) => (
          <ManuallyCreatedIndicator
            sources={[
              {
                label: 'Patient',
                createdByUserId: row.original.patient.created_by_user_id,
                createdBy: row.original.patient.created_by,
              },
              {
                label: 'Variant',
                createdByUserId: row.original.variant.created_by_user_id,
                createdBy: row.original.variant.created_by,
              },
              {
                label: 'Occurrence',
                createdByUserId: row.original.occurrence.created_by_user_id,
                createdBy: row.original.occurrence.created_by,
              },
            ]}
          />
        ),
      },
      {
        id: 'flags',
        header: '',
        size: 28,
        enableSorting: false,
        cell: ({ row }) => <FlagIndicator paperId={paperId} flags={rowFlags(flags, row.original)} />,
      },
      {
        id: 'expander',
        size: 40,
        enableSorting: false,
        header: () => null,
        cell: ({ row }) => (
          <RowExpander
            expanded={expandedCell?.rowId === String(row.original.occurrence.id)}
            onToggle={() => {
              const rowId = String(row.original.occurrence.id)
              setExpandedCell(expandedCell?.rowId === rowId ? null : { rowId, view: 'patient' })
            }}
          />
        ),
      },
      {
        id: 'patient',
        header: 'Patient',
        accessorFn: (row) => row.patient.identifier,
        cell: ({ row }) => {
          const { patient } = row.original
          return (
            <PatientIdCell
              paperId={paperId}
              patient={patient}
              onClick={() => toggleExpanded(String(row.original.occurrence.id), 'patient')}
            />
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
            <VariantLabel
              description={row.original.variant.variant_description}
              hgvsP={row.original.variant.hgvs_p}
            />
          </EntityLink>
        ),
      },
      {
        id: 'variant_type',
        header: 'Variant Type',
        accessorFn: (row) => row.variant.variant_type,
        cell: ({ row }) => <EditableVariantTypeCell paperId={paperId} variant={row.original.variant} />,
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
              <span>
                {row.original.pairedVariant ? (
                  <VariantLabel
                    description={row.original.pairedVariant.variant_description}
                    hgvsP={row.original.pairedVariant.hgvs_p}
                  />
                ) : (
                  '—'
                )}
              </span>
              <EvidencePopover block={occurrence.paired_variant_reasoning} />
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
  }, [rows, hasPairedVariants, paperId, expandedCell?.rowId, deleteMutation, flags])

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Linking ran but connected no patient to a variant.
      </p>
    )
  }

  return (
    <>
      <p className="text-sm text-muted-foreground mb-2">
        {probandOnly
          ? `${visibleRows.length} proband occurrence${visibleRows.length === 1 ? '' : 's'} of ${rows.length}`
          : `${rows.length} total occurrences`}
      </p>
      <DataTable
        columns={columns}
        data={visibleRows}
        filterPlaceholder="Filter occurrences..."
        toolbar={
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <Switch checked={probandOnly} onCheckedChange={setProbandOnly} />
            Proband only
            <span className="text-muted-foreground">({probandCount})</span>
          </label>
        }
        getRowId={(row) => String(row.occurrence.id)}
        getRowCanExpand={() => true}
        expandOnRowClick={false}
        getRowClassName={(row) =>
          isManuallyCreatedRow(row)
            ? 'bg-orange-50/60 dark:bg-orange-950/20'
            : rowFlags(flags, row).some((flag) => flag.resolved_at == null)
              ? 'bg-violet-50/60 dark:bg-violet-950/20'
              : undefined
        }
        expanded={expanded}
        onExpandedChange={() => {}}
        reveal={reveal}
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

/** What the Figure Descriptions tab can hold: the figure kinds extraction
 * reads for curation fields, as the tab's hover text. */
const FIGURE_DESCRIPTIONS_HINT =
  'The figures extraction reads: pedigrees, and genotyping images such as ' +
  'Sanger chromatograms, gels and restriction digests, copy-number plots ' +
  '(MLPA, array), sequencing read pileups, and karyotypes or FISH.'

export function ExtractionPage() {
  const params = useParams({ from: '/papers/$paperId/extraction' })
  const paperId = parseInt(params.paperId, 10)
  const {
    paper,
    rows,
    unassociatedPatients,
    unassociatedVariants,
    allPatients,
    allVariants,
    isLoading,
    isError,
    error,
  } = usePaperOccurrences(paperId)
  const flags = usePaperFlags(paperId)
  // The open tab lives in the URL so the papers table (and a pasted link)
  // can land on Families or Flags directly; the default stays out of it.
  const search = useSearch({ from: '/papers/$paperId/extraction' })
  const navigate = useNavigate({ from: '/papers/$paperId/extraction' })
  const tab: ExtractionTab = search.tab ?? DEFAULT_EXTRACTION_TAB
  const setTab = (next: string) => {
    if (!isExtractionTab(next)) return
    void navigate({ search: next === DEFAULT_EXTRACTION_TAB ? {} : { tab: next }, replace: true })
  }
  const [focus, setFocus] = useState<FlagTarget | null>(null)
  /** A flag's About chip: switch to the tab that shows the row, turn to its
   * page and open it. A patient or variant opens inside its first occurrence
   * (on its own panel) or, when it has none, in its Unassociated tab. A
   * family opens its row in the Families tab. */
  const navigateToTarget = (target: FlagTarget) => {
    const go = (next: ExtractionTab, to: FlagTarget) => {
      setFocus(to)
      setTab(next)
    }
    if (target.kind === 'occurrence') {
      go('occurrences', target)
    } else if (target.kind === 'patient') {
      const row = rows.find((r) => r.patient.id === target.id)
      if (row) go('occurrences', { kind: 'occurrence', id: row.occurrence.id, view: 'patient' })
      else go('unassociated-patients', target)
    } else if (target.kind === 'variant') {
      const row = rows.find((r) => r.variant.id === target.id)
      if (row) go('occurrences', { kind: 'occurrence', id: row.occurrence.id, view: 'variant' })
      else go('unassociated-variants', target)
    } else {
      go('families', target)
    }
  }
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

        <Tabs
          value={tab}
          onValueChange={(next) => {
            // The reader chose this tab: a stale chip target must not reopen
            // a row when they come back to it.
            setFocus(null)
            setTab(String(next))
          }}
        >
          <TabsList>
            <TabsTrigger value="occurrences">Occurrences</TabsTrigger>
            <TabsTrigger value="families">Families</TabsTrigger>
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
            <TabsTrigger value="flags">
              Flags
              {flags.open.length > 0 && (
                <span className="ml-1 text-xs text-violet-700 dark:text-violet-400">({flags.open.length})</span>
              )}
            </TabsTrigger>
            <Tooltip>
              <TooltipTrigger render={<TabsTrigger value="figures">Figure Descriptions</TabsTrigger>} />
              <TooltipContent className="max-w-xs">{FIGURE_DESCRIPTIONS_HINT}</TooltipContent>
            </Tooltip>
            <TabsTrigger value="paper-metadata">Paper Metadata</TabsTrigger>
          </TabsList>

          <TabsContent value="occurrences" className="pt-3">
            <PipelineGate
              tasks={tasks}
              task={TaskType.PATIENT_VARIANT_OCCURRENCES}
              label="Patient/variant linking"
            >
              <OccurrencesTab
                paperId={paperId}
                rows={rows}
                flags={flags}
                focus={focus?.kind === 'occurrence' ? focus : null}
              />
            </PipelineGate>
          </TabsContent>
          <TabsContent value="families" className="pt-3">
            <PipelineGate tasks={tasks} task={TaskType.PATIENT_EXTRACTION} label="Patient extraction">
              <FamiliesTab
                paperId={paperId}
                focus={focus?.kind === 'family' || focus?.kind === 'patient' ? focus : null}
              />
            </PipelineGate>
          </TabsContent>
          <TabsContent value="unassociated-patients" className="pt-3">
            <UnassociatedPatientsTab
              paperId={paperId}
              patients={unassociatedPatients}
              tasks={tasks}
              flags={flags}
              focus={focus}
            />
          </TabsContent>
          <TabsContent value="unassociated-variants" className="pt-3">
            <UnassociatedVariantsTab
              paperId={paperId}
              variants={unassociatedVariants}
              tasks={tasks}
              flags={flags}
              focus={focus}
            />
          </TabsContent>
          <TabsContent value="flags" className="pt-3">
            <FlagsTab
              paperId={paperId}
              patients={allPatients}
              variants={allVariants}
              rows={rows}
              onNavigate={navigateToTarget}
            />
          </TabsContent>
          <TabsContent value="figures" className="pt-3">
            <FiguresTab paperId={paperId} />
          </TabsContent>
          <TabsContent value="paper-metadata" className="pt-3 h-[70vh]">
            {paper && <PaperMetadataTab paper={paper} />}
          </TabsContent>
        </Tabs>
      </div>
    </PdfHighlightProvider>
  )
}
