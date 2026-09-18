/* Patients extracted from the paper that no occurrence links to a variant
 * yet -- either linking hasn't run, or it found nothing to link them to. */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import type { PatientResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'

export function UnassociatedPatientsTab({
  paperId,
  patients,
}: {
  paperId: number
  patients: PatientResp[]
}) {
  const columns: ColumnDef<PatientResp>[] = useMemo(
    () => [
      { id: 'identifier', header: 'Identifier', accessorFn: (row) => row.identifier },
      { id: 'proband', header: 'Proband', accessorFn: (row) => row.proband_status },
      { id: 'affected', header: 'Affected', accessorFn: (row) => row.affected_status },
      { id: 'sex', header: 'Sex at Birth', accessorFn: (row) => row.sex },
    ],
    [],
  )

  if (patients.length === 0) {
    return <p className="text-sm text-muted-foreground">Every extracted patient is linked to a variant.</p>
  }

  return (
    <DataTable
      columns={columns}
      data={patients}
      filterPlaceholder="Filter patients..."
      getRowId={(row) => String(row.id)}
      getRowCanExpand={() => true}
      renderSubComponent={({ row }) => <PatientDetailPanel paperId={paperId} patient={row} />}
    />
  )
}
