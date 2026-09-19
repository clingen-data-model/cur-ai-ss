/* Variants extracted from the paper that no occurrence links to a patient.
 *
 * Gated on linking: before it runs nothing is linked, so an unguarded empty
 * table here would claim the exact opposite of the truth. */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Dna } from 'lucide-react'
import { TaskType } from '@/api/generated/types.gen'
import type { TaskResp, VariantResp } from '@/api/generated/types.gen'
import { deleteVariantPapersPaperIdVariantsVariantIdDelete } from '@/api/generated'
import { DataTable } from '@/components/ui/data-table'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'
import { PipelineGate } from '@/components/PipelineGate'
import { AddVariantDialog } from '@/components/AddVariantDialog'
import { LinkPatientDialog } from '@/components/LinkPatientDialog'
import { DeleteIconButton } from '@/components/DeleteIconButton'
import { apiErrorMessage } from '@/lib/apiError'

export function UnassociatedVariantsTab({
  paperId,
  variants,
  tasks,
}: {
  paperId: number
  variants: VariantResp[]
  tasks: TaskResp[]
}) {
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: (variantId: number) =>
      deleteVariantPapersPaperIdVariantsVariantIdDelete({
        path: { paper_id: paperId, variant_id: variantId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['variants', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Variant deleted')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to delete variant')),
  })

  const columns: ColumnDef<VariantResp>[] = useMemo(
    () => [
      { id: 'variant', header: 'Variant', accessorFn: (row) => row.variant_description },
      { id: 'type', header: 'Type', accessorFn: (row) => row.variant_type },
      {
        id: 'main_focus',
        header: 'Main Focus',
        accessorFn: (row) => (row.main_focus ? 'Yes' : 'No'),
      },
      {
        id: 'actions',
        header: '',
        size: 76,
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <LinkPatientDialog
              paperId={paperId}
              variantId={row.original.id}
              variantDescription={row.original.variant_description}
            />
            <DeleteIconButton
              title="Delete variant?"
              description={
                <>
                  This will permanently delete{' '}
                  <span className="font-medium text-foreground">
                    {row.original.variant_description}
                  </span>{' '}
                  and all data linked to it. This cannot be undone.
                </>
              }
              onDelete={() => deleteMutation.mutate(row.original.id)}
            />
          </div>
        ),
      },
    ],
    [paperId, deleteMutation],
  )

  return (
    <PipelineGate
      tasks={tasks}
      task={TaskType.PATIENT_VARIANT_OCCURRENCES}
      label="Patient/variant linking"
    >
      {variants.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Dna />
            </EmptyMedia>
            <EmptyTitle>Every extracted variant is linked to a patient</EmptyTitle>
            <EmptyDescription>
              Add a variant manually if extraction missed one.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <AddVariantDialog paperId={paperId} />
          </EmptyContent>
        </Empty>
      ) : (
        <>
          <div className="flex justify-end mb-2">
            <AddVariantDialog paperId={paperId} />
          </div>
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
        </>
      )}
    </PipelineGate>
  )
}
