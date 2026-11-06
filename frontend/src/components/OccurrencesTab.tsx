/* The Occurrences table: one row per patient/variant link, editable inline,
 * with click-to-expand Patient/Variant detail panels. The extraction page's
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
import { displayProteinChange } from '@/lib/hgvs'
import { EntityLink } from '@/components/EntityLink'
import { PatientIdCell, hasSeveralFamilies } from '@/components/PatientIdCell'
import { RowExpander } from '@/components/RowExpander'
import { VariantHoverCardContent } from '@/components/VariantHoverCard'
import { DeleteIconButton } from '@/components/DeleteIconButton'
import { apiErrorMessage } from '@/lib/apiError'
import { ProbandStatus } from '@/api/generated/types.gen'
import { Switch } from '@/components/ui/switch'

type ExpandedView = 'patient' | 'variant' | 'occurrence'

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
  const severalFamilies = useMemo(() => hasSeveralFamilies(rows.map((r) => r.patient)), [rows])

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
                label: 'Individual',
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
        id: 'signoff',
        header: '',
        size: 28,
        enableSorting: false,
        cell: ({ row }) => (
          <SignoffMark rows={[row.original.occurrence]} />
        ),
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
              setExpandedCell(
                expandedCell?.rowId === rowId ? null : { rowId, view: compact ? 'occurrence' : 'patient' },
              )
            }}
          />
        ),
      },
    ]
    if (!compact) {
      // Its own column so the family sorts and the filter box matches it;
      // sorting by it puts a family's rows together. The compact table in
      // Review Mode is one family already.
      cols.push({
        id: 'family',
        header: 'Family',
        accessorFn: (row) => row.patient.family_identifier,
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground truncate">{row.original.patient.family_identifier}</span>
        ),
      })
    }
    cols.push(
      {
        id: 'patient',
        header: 'Individual',
        accessorFn: (row) => row.patient.identifier,
        cell: ({ row }) => {
          const { patient } = row.original
          return (
            <PatientIdCell
              paperId={paperId}
              patient={patient}
              showFamily={compact && severalFamilies}
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
    )
    if (!compact) {
      cols.push({
        id: 'variant_type',
        header: 'Variant Type',
        accessorFn: (row) => row.variant.variant_type,
        cell: ({ row }) => <EditableVariantTypeCell paperId={paperId} variant={row.original.variant} />,
      })
    }

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
        header: 'Inheritance mechanism',
        cell: ({ row }) => <EditableInheritanceCell paperId={paperId} occurrence={row.original.occurrence} />,
      },
      {
        id: 'de_novo',
        header: 'De Novo',
        cell: ({ row }) => <EditableDeNovoCell paperId={paperId} occurrence={row.original.occurrence} />,
      },
    )
    if (compact) return cols

    cols.push({
      id: 'testing_methods',
      header: 'Testing Methods',
      cell: ({ row }) => (
        <EditableTestingMethodsCell paperId={paperId} occurrence={row.original.occurrence} />
      ),
    })

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
              description="This will permanently delete this individual/variant link. This cannot be undone."
              onDelete={() => deleteMutation.mutate(occurrence.id)}
            />
          </div>
        )
      },
    })

    return cols
  }, [rows, hasPairedVariants, severalFamilies, paperId, expandedCell?.rowId, deleteMutation, flags, compact])

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
            ? `${visibleRows.length} proband occurrence${visibleRows.length === 1 ? '' : 's'} of ${rows.length}`
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
          ) : expandedCell?.view === 'occurrence' ? (
            <OccurrenceDetailPanel paperId={paperId} occurrence={row.occurrence} />
          ) : (
            <VariantDetailPanel paperId={paperId} variant={row.variant} />
          )
        }
      />
    </>
  )
}
