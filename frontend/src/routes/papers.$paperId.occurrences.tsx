/* Occurrences page: a read-only analog of the Streamlit "Occurrences" tab
 * (lib/ui/paper/occurrences.py) -- one row per patient/variant link, with a
 * detail panel for the selected row. Editing, evidence controls and PDF
 * highlighting are intentionally left for a later pass; this is the data
 * laid out the same way, without the interactive pieces.
 */
import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { useParams, Link } from '@tanstack/react-router'
import type { ColumnDef } from '@tanstack/react-table'
import { CheckIcon, XIcon } from 'lucide-react'
import { usePaperOccurrences } from '@/hooks/usePaperOccurrences'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { DataTable } from '@/components/ui/data-table'
import { Spinner } from '@/components/ui/spinner'
import { Badge } from '@/components/ui/badge'

function gnomadUrl(coordinates: string): string {
  return `https://gnomad.broadinstitute.org/variant/${coordinates}?dataset=gnomad_r4`
}

function DetailField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm border-b last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  )
}

function OccurrenceDetail({
  row,
  familiesById,
}: {
  row: OccurrenceRow
  familiesById: Map<number, { consanguinity: boolean }>
}) {
  const { occurrence, patient, pairedVariant } = row
  const harmonized = row.variant.harmonized_variant.value
  const family = familiesById.get(patient.family_id)

  return (
    <div className="p-4 space-y-4 bg-muted/30">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h4 className="text-sm font-semibold mb-2">Patient Info</h4>
          <DetailField label="Identifier" value={patient.identifier} />
          <DetailField label="Proband Status" value={patient.proband_status} />
          <DetailField label="Affected Status" value={patient.affected_status} />
          <DetailField label="Sex at Birth" value={patient.sex} />
          <DetailField label="Age at Diagnosis" value={patient.age_diagnosis ?? 'N/A'} />
          <DetailField label="Age at Report" value={patient.age_report ?? 'N/A'} />
          <DetailField label="Country of Origin" value={patient.country_of_origin} />
          <DetailField label="Race" value={patient.race} />
          <DetailField label="Ethnicity" value={patient.ethnicity} />
          <DetailField label="Consanguineous" value={family?.consanguinity ? 'Yes' : 'No'} />
        </div>
        <div>
          <h4 className="text-sm font-semibold mb-2">Harmonized Variant Info</h4>
          {harmonized ? (
            <>
              <DetailField label="HGVS g." value={harmonized.hgvs_g ?? 'N/A'} />
              <DetailField label="HGVS c." value={harmonized.hgvs_c ?? 'N/A'} />
              <DetailField label="HGVS p." value={harmonized.hgvs_p ?? 'N/A'} />
              <DetailField label="rsID" value={harmonized.rsid ?? 'N/A'} />
              <DetailField
                label="gnomAD-style"
                value={
                  harmonized.gnomad_style_coordinates ? (
                    <a
                      href={gnomadUrl(harmonized.gnomad_style_coordinates)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary hover:underline"
                    >
                      {harmonized.gnomad_style_coordinates}
                    </a>
                  ) : (
                    'N/A'
                  )
                }
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Harmonized variant data not available</p>
          )}
        </div>
      </div>

      {occurrence.disease_name && (
        <div>
          <h4 className="text-sm font-semibold mb-1">Disease Name</h4>
          <p className="text-sm">{occurrence.disease_name}</p>
        </div>
      )}

      {pairedVariant && (
        <div>
          <h4 className="text-sm font-semibold mb-1">Compound Heterozygous Pairing</h4>
          <p className="text-sm">
            Paired with <span className="font-medium">{pairedVariant.variant_description}</span>
            {occurrence.paired_variant_confidence && (
              <>
                {' '}
                — Confidence:{' '}
                <span className="font-medium capitalize">
                  {occurrence.paired_variant_confidence}
                </span>
              </>
            )}
          </p>
        </div>
      )}
    </div>
  )
}

export function OccurrencesPage() {
  const params = useParams({ from: '/papers/$paperId/occurrences' })
  const paperId = parseInt(params.paperId, 10)
  const { paper, rows, familiesById, isLoading, isError, error } = usePaperOccurrences(paperId)

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
      },
      {
        id: 'variant',
        header: 'Variant',
        accessorFn: (row) => row.variant.variant_description,
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
        accessorFn: (row) => row.occurrence.zygosity,
      },
      {
        id: 'inheritance',
        header: 'Inheritance',
        accessorFn: (row) => row.occurrence.inheritance,
      },
      {
        id: 'de_novo',
        header: 'De Novo',
        accessorFn: (row) => row.occurrence.de_novo,
        cell: ({ getValue }) =>
          getValue() ? (
            <CheckIcon className="size-4 text-emerald-600" />
          ) : (
            <XIcon className="size-4 text-muted-foreground" />
          ),
      },
      {
        id: 'testing_methods',
        header: 'Testing Methods',
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.occurrence.testing_methods.map((method) => (
              <Badge key={method} variant="secondary">
                {method}
              </Badge>
            ))}
          </div>
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
  }, [hasPairedVariants, hasDiseaseNames])

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
          getRowCanExpand={() => true}
          renderSubComponent={({ row }) => (
            <OccurrenceDetail row={row} familiesById={familiesById} />
          )}
        />
      )}
    </div>
  )
}
