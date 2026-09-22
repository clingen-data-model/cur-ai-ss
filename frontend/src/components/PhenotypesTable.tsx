/* All phenotypes for a patient, one row per phenotype -- a table rather than
 * the accordion this replaced, so every concept, its HPO match, and the
 * match's id are all visible/scannable at once instead of one at a time
 * behind a click, and the id can be copied straight out of the row. */
import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { toast } from 'sonner'
import { getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet } from '@/api/generated'
import type { PhenotypeResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { EvidencePopover } from '@/components/EvidencePopover'
import { CopyButton } from '@/components/CopyButton'
import { AddPhenotypeDialog } from '@/components/AddPhenotypeDialog'
import { RelinkHpoDialog } from '@/components/RelinkHpoDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Copy, Download } from 'lucide-react'

const STALE_TIME = 5 * 60 * 1000

function toCsvField(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

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

  const copyAllHpoIds = useCallback(async () => {
    if (!phenotypesQuery.data) return

    const ids = phenotypesQuery.data
      .map((p) => p.hpo.value?.id)
      .filter(Boolean)
      .join('\n')

    if (!ids) {
      toast.info('No HPO IDs to copy')
      return
    }

    try {
      await navigator.clipboard.writeText(ids)
      toast.success(`Copied ${ids.split('\n').length} HPO IDs`)
    } catch {
      toast.error('Failed to copy')
    }
  }, [phenotypesQuery.data])

  const exportCsv = () => {
    if (!phenotypesQuery.data) return

    const header = ['Phenotype', 'HPO Match', 'HPO ID', 'Details']
    const rows = phenotypesQuery.data.map((p) => [
      p.concept,
      p.hpo.value?.name ?? '',
      p.hpo.value?.id ?? '',
      additionalInfo(p),
    ])
    const csv = [header, ...rows].map((row) => row.map(toCsvField).join(',')).join('\n')

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `phenotypes_patient_${patientId}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

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
        header: () => (
          <div className="flex items-center gap-1.5">
            <span>HPO ID</span>
            <button
              type="button"
              onClick={copyAllHpoIds}
              title="Copy all HPO IDs"
              className="inline-flex items-center justify-center size-5 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
            >
              <Copy className="size-3.5" />
            </button>
          </div>
        ),
        enableSorting: false,
        accessorFn: (row) => row.hpo.value?.id ?? '',
        cell: ({ row }) => {
          const phenotype = row.original
          const hpo = phenotype.hpo.value
          const id = hpo?.id
          return (
            <div className="flex items-center gap-1">
              {id ? (
                <>
                  <a
                    href={`https://hpo.jax.org/app/browse/term/${id}${hpo.name ? `#${hpo.name}` : ''}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-link hover:underline"
                  >
                    <code className="text-xs">{id}</code>
                  </a>
                  <CopyButton value={id} />
                </>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
              <RelinkHpoDialog
                paperId={paperId}
                phenotypeId={phenotype.id}
                concept={phenotype.concept}
                currentHpoId={hpo?.id ?? null}
                currentHpoName={hpo?.name ?? null}
              />
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
    [paperId, copyAllHpoIds],
  )

  if (phenotypesQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Loading phenotypes…</p>
  }

  if (!phenotypesQuery.data || phenotypesQuery.data.length === 0) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold">Phenotypes</h4>
          <AddPhenotypeDialog paperId={paperId} patientId={patientId} />
        </div>
        <p className="text-sm text-muted-foreground">No phenotypes extracted.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Phenotypes</h4>
        <div className="flex items-center gap-2">
          <AddPhenotypeDialog paperId={paperId} patientId={patientId} />
          <Button variant="outline" size="sm" onClick={exportCsv} className="gap-2">
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </div>
      <DataTable
        columns={columns}
        data={phenotypesQuery.data}
        filterPlaceholder="Filter phenotypes..."
        getRowId={(row) => String(row.id)}
      />
    </div>
  )
}
