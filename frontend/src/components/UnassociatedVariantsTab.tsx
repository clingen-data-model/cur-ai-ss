/* Variants extracted from the paper that no occurrence links to a patient.
 *
 * Gated on linking: before it runs nothing is linked, so an unguarded empty
 * table here would claim the exact opposite of the truth. */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { TaskType } from '@/api/generated/types.gen'
import type { TaskResp, VariantResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'
import { PipelineGate } from '@/components/PipelineGate'

export function UnassociatedVariantsTab({
  paperId,
  variants,
  tasks,
}: {
  paperId: number
  variants: VariantResp[]
  tasks: TaskResp[]
}) {
  const columns: ColumnDef<VariantResp>[] = useMemo(
    () => [
      { id: 'variant', header: 'Variant', accessorFn: (row) => row.variant_description },
      { id: 'type', header: 'Type', accessorFn: (row) => row.variant_type },
      {
        id: 'main_focus',
        header: 'Main Focus',
        accessorFn: (row) => (row.main_focus ? 'Yes' : 'No'),
      },
    ],
    [],
  )

  return (
    <PipelineGate
      tasks={tasks}
      task={TaskType.PATIENT_VARIANT_OCCURRENCES}
      label="Patient/variant linking"
    >
      {variants.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Every extracted variant is linked to a patient.
        </p>
      ) : (
        <DataTable
          columns={columns}
          data={variants}
          filterPlaceholder="Filter variants..."
          getRowId={(row) => String(row.id)}
          getRowCanExpand={() => true}
          renderSubComponent={({ row }) => (
            <VariantDetailPanel paperId={paperId} variant={row} />
          )}
        />
      )}
    </PipelineGate>
  )
}
