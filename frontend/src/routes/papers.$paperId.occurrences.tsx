/* Occurrences page: the SPA analog of the Streamlit "Occurrences" tab
 * (lib/ui/paper/occurrences.py) -- one row per patient/variant link.
 * Zygosity, Inheritance, De Novo and Testing Methods are editable inline;
 * clicking the Patient or Variant identifier expands the row into that
 * entity's full field set (lib/ui/paper/patients.py / variants.py), also
 * editable. Every manual edit is gated behind a forced human-edit-note
 * dialog (see HumanEditNoteDialog).
 */
import { useMemo, useState } from 'react'
import { useParams, Link } from '@tanstack/react-router'
import type { ColumnDef, ExpandedState } from '@tanstack/react-table'
import { usePaperOccurrences } from '@/hooks/usePaperOccurrences'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { DataTable } from '@/components/ui/data-table'
import { Spinner } from '@/components/ui/spinner'
import {
  EditableDeNovoCell,
  EditableInheritanceCell,
  EditableTestingMethodsCell,
  EditableZygosityCell,
} from '@/components/OccurrenceEditableCells'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'

type ExpandedView = 'patient' | 'variant'

function EntityLink({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className="text-left hover:underline underline-offset-2 cursor-pointer"
    >
      {children}
    </button>
  )
}

export function OccurrencesPage() {
  const params = useParams({ from: '/papers/$paperId/occurrences' })
  const paperId = parseInt(params.paperId, 10)
  const { paper, rows, isLoading, isError, error } = usePaperOccurrences(paperId)

  const [expandedCell, setExpandedCell] = useState<{ rowId: string; view: ExpandedView } | null>(null)

  const toggleExpanded = (rowId: string, view: ExpandedView) => {
    setExpandedCell((prev) => (prev?.rowId === rowId && prev.view === view ? null : { rowId, view }))
  }

  const expanded: ExpandedState = expandedCell ? { [expandedCell.rowId]: true } : {}

  const hasPairedVariants = useMemo(() => rows.some((r) => r.pairedVariant), [rows])
  const hasDiseaseNames = useMemo(
    () => rows.some((r) => r.occurrence.disease_name),
    [rows],
  )

  const columns: ColumnDef<OccurrenceRow>[] = useMemo(() => {
    const cols: ColumnDef<OccurrenceRow>[] = [
      {
        id: 'proband',
        header: 'Proband',
        accessorFn: (row) => row.patient.proband_status,
      },
      {
        id: 'affected',
        header: 'Affected',
        accessorFn: (row) => row.patient.affected_status,
      },
      {
        id: 'patient',
        header: 'Patient',
        accessorFn: (row) => row.patient.identifier,
        cell: ({ row }) => (
          <EntityLink onClick={() => toggleExpanded(String(row.original.occurrence.id), 'patient')}>
            {row.original.patient.identifier}
          </EntityLink>
        ),
      },
      {
        id: 'variant',
        header: 'Variant',
        accessorFn: (row) => row.variant.variant_description,
        cell: ({ row }) => (
          <EntityLink onClick={() => toggleExpanded(String(row.original.occurrence.id), 'variant')}>
            {row.original.variant.variant_description}
          </EntityLink>
        ),
      },
    ]

    if (hasPairedVariants) {
      cols.push({
        id: 'paired_variant',
        header: 'Paired Variant',
        accessorFn: (row) => row.pairedVariant?.variant_description ?? '',
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

    if (hasDiseaseNames) {
      cols.push({
        id: 'disease_name',
        header: 'Disease Name',
        accessorFn: (row) => row.occurrence.disease_name ?? '',
      })
    }

    return cols
  }, [hasPairedVariants, hasDiseaseNames, paperId])

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
    <div className="space-y-4">
      <div>
        <Link to="/" className="text-sm text-muted-foreground hover:underline">
          &larr; All Papers
        </Link>
        <h1 className="text-xl font-semibold mt-1">
          {paper?.title ?? paper?.filename} — Patient/Variant Occurrences
        </h1>
        <p className="text-sm text-muted-foreground">{rows.length} total occurrences</p>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No Patient/Variant links found.</p>
      ) : (
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
      )}
    </div>
  )
}
