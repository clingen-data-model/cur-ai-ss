/* All phenotypes for a patient, one row per phenotype -- a table rather than
 * the accordion this replaced, so every concept, its HPO match, and the
 * match's id are all visible/scannable at once instead of one at a time
 * behind a click, and the id can be copied straight out of the row. */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet } from '@/api/generated'
import type { PhenotypeResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { EvidencePopover } from '@/components/EvidencePopover'
import { CopyButton } from '@/components/CopyButton'
import { Badge } from '@/components/ui/badge'

const STALE_TIME = 5 * 60 * 1000

function additionalInfo(phenotype: PhenotypeResp): string {
  return [
    phenotype.onset && `Onset: ${phenotype.onset}`,
    phenotype.location && `Location: ${phenotype.location}`,
    phenotype.severity && `Severity: ${phenotype.severity}`,
    phenotype.modifier && `Modifier: ${phenotype.modifier}`,
  ]
    .filter(Boolean)
    .join(' · ')
}

export function PhenotypesTable({ paperId, patientId }: { paperId: number; patientId: number }) {
  const phenotypesQuery = useQuery({
    queryKey: ['phenotypes', paperId, patientId],
    queryFn: () =>
      getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet({
        path: { paper_id: paperId, patient_id: patientId },
      }),
    staleTime: STALE_TIME,
  })

  const columns: ColumnDef<PhenotypeResp>[] = useMemo(
    () => [
      {
        id: 'concept',
        header: 'Phenotype',
        accessorFn: (row) => row.concept,
        cell: ({ row }) => {
          const phenotype = row.original
          return (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span>{phenotype.concept}</span>
              {phenotype.negated && (
                <Badge variant="outline" className="text-[10px]">
                  Negated
                </Badge>
              )}
              {phenotype.uncertain && (
                <Badge variant="outline" className="text-[10px]">
                  Uncertain
                </Badge>
              )}
              {phenotype.family_history && (
                <Badge variant="outline" className="text-[10px]">
                  Family history
                </Badge>
              )}
              <EvidencePopover block={phenotype.concept_evidence} />
            </div>
          )
        },
      },
      {
        id: 'hpo_match',
        header: 'HPO Match',
        accessorFn: (row) => row.hpo.value?.name ?? '',
        cell: ({ row }) => {
          const hpo = row.original.hpo
          return (
            <div className="flex items-center gap-1.5">
              <span className={hpo.value ? undefined : 'text-muted-foreground'}>
                {hpo.value ? hpo.value.name : 'No match found'}
              </span>
              <EvidencePopover block={hpo} />
            </div>
          )
        },
      },
      {
        id: 'hpo_id',
        header: 'HPO ID',
        accessorFn: (row) => row.hpo.value?.id ?? '',
        cell: ({ row }) => {
          const id = row.original.hpo.value?.id
          if (!id) return <span className="text-muted-foreground">—</span>
          return (
            <div className="flex items-center gap-1">
              <code className="text-xs">{id}</code>
              <CopyButton value={id} />
            </div>
          )
        },
      },
      {
        id: 'details',
        header: 'Details',
        enableSorting: false,
        cell: ({ row }) => <span className="text-xs text-muted-foreground">{additionalInfo(row.original) || '—'}</span>,
      },
    ],
    [],
  )

  if (phenotypesQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Loading phenotypes…</p>
  }

  if (!phenotypesQuery.data || phenotypesQuery.data.length === 0) {
    return <p className="text-sm text-muted-foreground">No phenotypes extracted.</p>
  }

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold">Phenotypes</h4>
      <DataTable
        columns={columns}
        data={phenotypesQuery.data}
        filterPlaceholder="Filter phenotypes..."
        getRowId={(row) => String(row.id)}
      />
    </div>
  )
}
