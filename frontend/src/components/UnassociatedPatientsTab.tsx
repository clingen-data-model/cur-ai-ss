/* Patients extracted from the paper that no occurrence links to a variant.
 *
 * Gated on linking: before it runs nothing is linked, so an unguarded empty
 * table here would claim the exact opposite of the truth. */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { UserPlus } from 'lucide-react'
import { TaskType } from '@/api/generated/types.gen'
import type { PatientResp, TaskResp } from '@/api/generated/types.gen'
import { deletePatientPapersPaperIdPatientsPatientIdDelete } from '@/api/generated'
import { DataTable } from '@/components/ui/data-table'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'
import { PipelineGate } from '@/components/PipelineGate'
import { AddPatientDialog } from '@/components/AddPatientDialog'
import { DeleteIconButton } from '@/components/DeleteIconButton'
import { apiErrorMessage } from '@/lib/apiError'

export function UnassociatedPatientsTab({
  paperId,
  patients,
  tasks,
}: {
  paperId: number
  patients: PatientResp[]
  tasks: TaskResp[]
}) {
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: (patientId: number) =>
      deletePatientPapersPaperIdPatientsPatientIdDelete({
        path: { paper_id: paperId, patient_id: patientId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['patients', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Patient deleted')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to delete patient')),
  })

  const columns: ColumnDef<PatientResp>[] = useMemo(
    () => [
      { id: 'identifier', header: 'Identifier', accessorFn: (row) => row.identifier },
      { id: 'proband', header: 'Proband', accessorFn: (row) => row.proband_status },
      { id: 'affected', header: 'Affected', accessorFn: (row) => row.affected_status },
      { id: 'sex', header: 'Sex at Birth', accessorFn: (row) => row.sex },
      {
        id: 'actions',
        header: '',
        size: 40,
        enableSorting: false,
        cell: ({ row }) => (
          <DeleteIconButton
            title="Delete patient?"
            description={
              <>
                This will permanently delete{' '}
                <span className="font-medium text-foreground">{row.original.identifier}</span>{' '}
                and all data linked to it. This cannot be undone.
              </>
            }
            onDelete={() => deleteMutation.mutate(row.original.id)}
          />
        ),
      },
    ],
    [deleteMutation],
  )

  return (
    <PipelineGate
      tasks={tasks}
      task={TaskType.PATIENT_VARIANT_OCCURRENCES}
      label="Patient/variant linking"
    >
      {patients.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <UserPlus />
            </EmptyMedia>
            <EmptyTitle>Every extracted patient is linked to a variant</EmptyTitle>
            <EmptyDescription>
              Add a patient manually if extraction missed one.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <AddPatientDialog paperId={paperId} />
          </EmptyContent>
        </Empty>
      ) : (
        <>
          <div className="flex justify-end mb-2">
            <AddPatientDialog paperId={paperId} />
          </div>
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
        </>
      )}
    </PipelineGate>
  )
}
