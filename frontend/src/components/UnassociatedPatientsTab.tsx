/* Patients extracted from the paper that no occurrence links to a variant.
 *
 * Gated on linking: before it runs nothing is linked, so an unguarded empty
 * table here would claim the exact opposite of the truth. */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { TaskType } from '@/api/generated/types.gen'
import type { PatientResp, TaskResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'
import { PipelineGate } from '@/components/PipelineGate'

export function UnassociatedPatientsTab({
  paperId,
  patients,
  tasks,
}: {
  paperId: number
  patients: PatientResp[]
  tasks: TaskResp[]
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

  return (
    <PipelineGate
      tasks={tasks}
      task={TaskType.PATIENT_VARIANT_OCCURRENCES}
      label="Patient/variant linking"
    >
      {patients.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Every extracted patient is linked to a variant.
        </p>
      ) : (
        <DataTable
          columns={columns}
          data={patients}
          filterPlaceholder="Filter patients..."
          getRowId={(row) => String(row.id)}
          getRowCanExpand={() => true}
          renderSubComponent={({ row }) => (
            <PatientDetailPanel paperId={paperId} patient={row} />
          )}
        />
      )}
    </PipelineGate>
  )
}
