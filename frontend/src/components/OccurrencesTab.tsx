/* The Occurrences table: one row per patient/variant link, editable inline,
 * with click-to-expand Patient/Variant detail panels. A compound-het pair is
 * the exception: its two occurrences share one row, the individual shown
 * once and the two variants on two lines, each with its own fields beside
 * it (see TableRow below). The extraction page's
 * main tab, and the review walk's view of one case's rows
 * (routes/papers.$paperId.review.tsx), which is why it lives here rather
 * than in the extraction route: the walk shows a case the way the paper
 * page shows the paper, same columns, same row markers (curator-created,
 * flags, sign-off), same panels.
 */
import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef, ExpandedState } from '@tanstack/react-table'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import type { FlagIndex } from '@/hooks/usePaperFlags'
import { FlagIndicator } from '@/components/FlagIndicator'
import { SignoffMark } from '@/components/SignoffMark'
import type { FlagTarget } from '@/lib/flagTarget'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { deleteOccurrencePapersPaperIdOccurrencesOccurrenceIdDelete } from '@/api/generated'
import { DataTable } from '@/components/ui/data-table'
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
import { OccurrenceDetailPanel } from '@/components/OccurrenceDetailPanel'
import { VariantLabel } from '@/components/VariantLabel'
import { EntityLink } from '@/components/EntityLink'
import { PatientIdCell, hasSeveralFamilies } from '@/components/PatientIdCell'
import { RowExpander } from '@/components/RowExpander'
import { VariantHoverCardContent } from '@/components/VariantHoverCard'
import { DeleteIconButton } from '@/components/DeleteIconButton'
import { apiErrorMessage } from '@/lib/apiError'
import { ProbandStatus } from '@/api/generated/types.gen'
import { Switch } from '@/components/ui/switch'

type ExpandedView = 'patient' | 'variant' | 'occurrence'

/** What the table draws as one row: one occurrence, or the two of a
 * compound-het pair. They used to be two rows, each naming the other in a
 * Paired Variant column, which read as the same fact twice. The occurrences
 * stay separate records with their own zygosity, parent of origin and
 * sign-off, so every per-occurrence cell stacks one line per occurrence
 * (Lines) rather than choosing one to show. The row's id is its first
 * occurrence's. */
interface TableRow {
  lines: OccurrenceRow[]
}

/** Fold each pair into one row, at the position of whichever half comes
 * first. A half whose partner is not among `rows` (a filtered view) stays a
 * row of its own. */
function mergePairs(rows: OccurrenceRow[]): TableRow[] {
  const byId = new Map(rows.map((r) => [r.occurrence.id, r]))
  const placed = new Set<number>()
  const merged: TableRow[] = []
  for (const row of rows) {
    if (placed.has(row.occurrence.id)) continue
    placed.add(row.occurrence.id)
    const partnerId = row.occurrence.paired_variant_link_id
    const partner = partnerId != null && !placed.has(partnerId) ? byId.get(partnerId) : undefined
    if (partner) placed.add(partner.occurrence.id)
    merged.push({ lines: partner ? [row, partner] : [row] })
  }
  return merged
}

const rowIdOf = (row: TableRow) => String(row.lines[0].occurrence.id)

/** One line per occurrence of the row, each a fixed minimum height (the
 * editable cells' h-7) so a pair's lines sit level across the columns. */
function Lines({ row, children }: { row: TableRow; children: (line: OccurrenceRow) => React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      {row.lines.map((line) => (
        <div key={line.occurrence.id} className="flex min-h-7 items-center">
          {children(line)}
        </div>
      ))}
    </div>
  )
}

/** Same "any of patient/variant/occurrence was curator-created" check as
 * ManuallyCreatedIndicator, reused to tint the whole row -- the icon alone
 * sits in a narrow, unlabeled column that's easy to miss. */
function isManuallyCreatedRow(row: TableRow): boolean {
  return row.lines.some(
    (line) =>
      line.patient.created_by_user_id != null ||
      line.variant.created_by_user_id != null ||
      line.occurrence.created_by_user_id != null,
  )
}

/** Every flag that touches an occurrence row: the occurrence's own, plus
 * the patient's and the variant's, since this tab is where both are read. */
function rowFlags(flags: FlagIndex, row: TableRow) {
  const seen = new Set<number>()
  return row.lines
    .flatMap((line) => [
      ...(flags.byOccurrence.get(line.occurrence.id) ?? []),
      ...(flags.byPatient.get(line.patient.id) ?? []),
      ...(flags.byVariant.get(line.variant.id) ?? []),
    ])
    .filter((flag) => !seen.has(flag.id) && seen.add(flag.id))
}

function isProbandRow(row: OccurrenceRow): boolean {
  return row.patient.proband_status === ProbandStatus.PROBAND
}

export function OccurrencesTab({
  paperId,
  rows,
  flags,
  focus,
  compact = false,
}: {
  paperId: number
  rows: OccurrenceRow[]
  flags: FlagIndex
  /** The review rail's form: the occurrence's own columns (patient, variant,
   * zygosity, inheritance, de novo) and the row icons, without the count,
   * the search box, the proband toggle, the variant type, testing methods,
   * disease columns or the pair/delete actions, so a row fits half a
   * viewport. The Patient and Variant panels behind the names are the same;
   * the caret opens the Occurrence panel, which holds the dropped fields. */
  compact?: boolean
  /** An occurrence to open on arrival (from a flag's About chip), on the
   * panel the chip names. A new object is a new request, so the same row can
   * be asked for again after the reader has closed it. */
  focus?: Extract<FlagTarget, { kind: 'occurrence' }> | null
}) {
  const queryClient = useQueryClient()
  const tableRows = useMemo(() => mergePairs(rows), [rows])
  /** The row an occurrence is drawn in: its own, or its pair's. */
  const rowIdFor = (occurrenceId: number) => {
    const row = tableRows.find((r) => r.lines.some((l) => l.occurrence.id === occurrenceId))
    return row ? rowIdOf(row) : String(occurrenceId)
  }
  // The open panel: which row, and which of the row's occurrences it is
  // about (a pair's two variants each open their own Variant panel).
  const [expandedCell, setExpandedCell] = useState<{
    rowId: string
    occurrenceId: number
    view: ExpandedView
  } | null>(
    focus ? { rowId: rowIdFor(focus.id), occurrenceId: focus.id, view: focus.view ?? 'patient' } : null,
  )
  // Proband-only view: the probands' rows alone, the relatives hidden. Plain
  // page state like the table's search box, and lifted the same way the
  // search is when a flag chip names a relative's row, rather than scrolling
  // to a row that is not there.
  const [probandOnly, setProbandOnly] = useState(false)
  useEffect(() => {
    if (!focus) return
    setExpandedCell({ rowId: rowIdFor(focus.id), occurrenceId: focus.id, view: focus.view ?? 'patient' })
    const target = rows.find((r) => r.occurrence.id === focus.id)
    if (target && !isProbandRow(target)) setProbandOnly(false)
    // rows is read, not watched: a data refresh must not re-open the row.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reveal = useMemo(() => (focus ? { rowId: rowIdFor(focus.id) } : null), [focus])
  const probandCount = useMemo(() => rows.filter(isProbandRow).length, [rows])
  // Counted in occurrences, as the line above the table is; drawn as rows.
  const visibleCount = probandOnly ? probandCount : rows.length
  const visibleRows = useMemo(
    () => (probandOnly ? tableRows.filter((row) => isProbandRow(row.lines[0])) : tableRows),
    [tableRows, probandOnly],
  )

  const toggleExpanded = (row: TableRow, line: OccurrenceRow, view: ExpandedView) => {
    const occurrenceId = line.occurrence.id
    setExpandedCell((prev) =>
      prev?.occurrenceId === occurrenceId && prev.view === view
        ? null
        : { rowId: rowIdOf(row), occurrenceId, view },
    )
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

  const severalFamilies = useMemo(() => hasSeveralFamilies(rows.map((r) => r.patient)), [rows])

  const columns: ColumnDef<TableRow>[] = useMemo(() => {
    const cols: ColumnDef<TableRow>[] = [
      {
        id: 'created',
        header: '',
        size: 28,
        enableSorting: false,
        cell: ({ row }) => (
          <ManuallyCreatedIndicator
            sources={[
              {
                label: 'Individual',
                createdByUserId: row.original.lines[0].patient.created_by_user_id,
                createdBy: row.original.lines[0].patient.created_by,
              },
              ...row.original.lines.flatMap((line) => [
                {
                  label: 'Variant',
                  createdByUserId: line.variant.created_by_user_id,
                  createdBy: line.variant.created_by,
                },
                {
                  label: 'Occurrence',
                  createdByUserId: line.occurrence.created_by_user_id,
                  createdBy: line.occurrence.created_by,
                },
              ]),
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
        id: 'signoff',
        header: '',
        size: 28,
        enableSorting: false,
        cell: ({ row }) => (
          <SignoffMark
            rows={row.original.lines.map((line) => line.occurrence)}
            labels={row.original.lines.map((line) => line.variant.variant_description)}
          />
        ),
      },
      {
        id: 'expander',
        size: 40,
        enableSorting: false,
        header: () => null,
        cell: ({ row }) => (
          <RowExpander
            expanded={expandedCell?.rowId === rowIdOf(row.original)}
            onToggle={() => {
              const rowId = rowIdOf(row.original)
              setExpandedCell(
                expandedCell?.rowId === rowId
                  ? null
                  : {
                      rowId,
                      occurrenceId: row.original.lines[0].occurrence.id,
                      view: compact ? 'occurrence' : 'patient',
                    },
              )
            }}
          />
        ),
      },
    ]
    cols.push(
      {
        id: 'patient',
        header: 'Individual',
        // The family is printed beside the name, as in Unassociated
        // Individuals, rather than in a column of its own. It leads the sort
        // key, so sorting by Individual still puts a family's rows together,
        // and the filter box matches it.
        accessorFn: (row) =>
          `${row.lines[0].patient.family_identifier ?? ''} ${row.lines[0].patient.identifier}`,
        cell: ({ row }) => (
          <PatientIdCell
            paperId={paperId}
            patient={row.original.lines[0].patient}
            showFamily={severalFamilies}
            onClick={() => toggleExpanded(row.original, row.original.lines[0], 'patient')}
          />
        ),
      },
      {
        id: 'variant',
        header: 'Variant',
        // Both of a pair's variants, so the filter box finds the row by either.
        accessorFn: (row) => row.lines.map((line) => line.variant.variant_description).join(' '),
        cell: ({ row }) => (
          <Lines row={row.original}>
            {(line) => (
              <span className="flex items-center gap-1">
                {/* Opens this line's Variant panel, as clicking the name
                    does; a pair's two variants each have their own. */}
                <RowExpander
                  expanded={
                    expandedCell?.occurrenceId === line.occurrence.id && expandedCell.view === 'variant'
                  }
                  onToggle={() => toggleExpanded(row.original, line, 'variant')}
                />
                <EntityLink
                  onClick={() => toggleExpanded(row.original, line, 'variant')}
                  hoverContent={<VariantHoverCardContent variant={line.variant} />}
                >
                  <VariantLabel description={line.variant.variant_description} hgvsP={line.variant.hgvs_p} />
                </EntityLink>
                {/* Why the two are a compound-het pair. Each half carries
                    the same block; the first line shows it. */}
                {row.original.lines.length > 1 && line === row.original.lines[0] && (
                  <EvidencePopover block={line.occurrence.paired_variant_reasoning} />
                )}
              </span>
            )}
          </Lines>
        ),
      },
    )
    if (!compact) {
      cols.push({
        id: 'variant_type',
        header: 'Variant Type',
        accessorFn: (row) => row.lines.map((line) => line.variant.variant_type).join(' '),
        cell: ({ row }) => (
          <Lines row={row.original}>
            {(line) => <EditableVariantTypeCell paperId={paperId} variant={line.variant} />}
          </Lines>
        ),
      })
    }

    cols.push(
      {
        id: 'zygosity',
        header: 'Zygosity',
        cell: ({ row }) => (
          <Lines row={row.original}>
            {(line) => <EditableZygosityCell paperId={paperId} occurrence={line.occurrence} />}
          </Lines>
        ),
      },
      {
        id: 'inheritance',
        header: 'Inheritance mechanism',
        cell: ({ row }) => (
          <Lines row={row.original}>
            {(line) => <EditableInheritanceCell paperId={paperId} occurrence={line.occurrence} />}
          </Lines>
        ),
      },
      {
        id: 'de_novo',
        header: 'De Novo',
        cell: ({ row }) => (
          <Lines row={row.original}>
            {(line) => <EditableDeNovoCell paperId={paperId} occurrence={line.occurrence} />}
          </Lines>
        ),
      },
    )
    if (compact) return cols

    cols.push({
      id: 'testing_methods',
      header: 'Testing Methods',
      cell: ({ row }) => (
        <Lines row={row.original}>
          {(line) => <EditableTestingMethodsCell paperId={paperId} occurrence={line.occurrence} />}
        </Lines>
      ),
    })

    cols.push({
      id: 'disease_name',
      header: 'Disease Name',
      cell: ({ row }) => (
        <Lines row={row.original}>
          {(line) => <EditableDiseaseNameCell paperId={paperId} occurrence={line.occurrence} />}
        </Lines>
      ),
    })

    cols.push({
      id: 'mondo',
      header: 'MONDO Disease',
      cell: ({ row }) => (
        <Lines row={row.original}>{(line) => <MondoDiseaseCell occurrence={line.occurrence} />}</Lines>
      ),
    })

    cols.push({
      id: 'actions',
      header: '',
      size: 64,
      enableSorting: false,
      cell: ({ row }) => (
        // Per occurrence, a pair's two included: pairing, unpairing and
        // deleting each act on one patient/variant link.
        <Lines row={row.original}>
          {({ occurrence }) => (
            <div className="flex items-center gap-0.5">
              <PairOccurrenceDialog
                paperId={paperId}
                occurrence={occurrence}
                siblingOccurrences={rows.filter(
                  (r) =>
                    r.occurrence.patient_id === occurrence.patient_id &&
                    r.occurrence.id !== occurrence.id,
                )}
              />
              <DeleteIconButton
                title="Delete occurrence?"
                description="This will permanently delete this individual/variant link. This cannot be undone."
                onDelete={() => deleteMutation.mutate(occurrence.id)}
              />
            </div>
          )}
        </Lines>
      ),
    })

    return cols
  }, [rows, severalFamilies, paperId, expandedCell?.rowId, expandedCell?.occurrenceId, expandedCell?.view, deleteMutation, flags, compact])

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Linking ran but connected no individual to a variant.
      </p>
    )
  }

  return (
    <>
      {!compact && (
        <p className="text-sm text-muted-foreground mb-2">
          {probandOnly
            ? `${visibleCount} proband occurrence${visibleCount === 1 ? '' : 's'} of ${rows.length}`
            : `${rows.length} total occurrences`}
        </p>
      )}
      <DataTable
        columns={columns}
        data={visibleRows}
        compact={compact}
        filterPlaceholder="Filter occurrences..."
        toolbar={
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <Switch checked={probandOnly} onCheckedChange={setProbandOnly} />
            Proband only
            <span className="text-muted-foreground">({probandCount})</span>
          </label>
        }
        getRowId={rowIdOf}
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
        renderSubComponent={({ row }) => {
          const line =
            row.lines.find((l) => l.occurrence.id === expandedCell?.occurrenceId) ?? row.lines[0]
          return expandedCell?.view === 'patient' ? (
            <PatientDetailPanel paperId={paperId} patient={line.patient} />
          ) : expandedCell?.view === 'occurrence' ? (
            <OccurrenceDetailPanel paperId={paperId} occurrence={line.occurrence} />
          ) : (
            <VariantDetailPanel paperId={paperId} variant={line.variant} />
          )
        }}
      />
    </>
  )
}
