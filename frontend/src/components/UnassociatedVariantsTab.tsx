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
import { ManuallyCreatedIndicator } from '@/components/ManuallyCreatedIndicator'
import { FlagIndicator } from '@/components/FlagIndicator'
import type { FlagIndex } from '@/hooks/usePaperFlags'
import type { FlagTarget } from '@/lib/flagTarget'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'
import { VariantHoverCardContent } from '@/components/VariantHoverCard'
import { VariantLabel } from '@/components/VariantLabel'
import { EditableVariantTypeCell } from '@/components/OccurrenceEditableCells'
import { EntityLink } from '@/components/EntityLink'
import { RowExpander } from '@/components/RowExpander'
import { PipelineGate } from '@/components/PipelineGate'
import { AddVariantDialog } from '@/components/AddVariantDialog'
import { LinkPatientDialog } from '@/components/LinkPatientDialog'
import { DeleteIconButton } from '@/components/DeleteIconButton'
import { apiErrorMessage } from '@/lib/apiError'

export function UnassociatedVariantsTab({
  paperId,
  variants,
  tasks,
  flags,
  focus,
}: {
  paperId: number
  variants: VariantResp[]
  tasks: TaskResp[]
  flags: FlagIndex
  /** A variant to open on arrival (from a flag's About chip). */
  focus?: FlagTarget | null
}) {
  const queryClient = useQueryClient()
  const reveal = useMemo(
    () => (focus?.kind === 'variant' ? { rowId: String(focus.id) } : null),
    [focus],
  )

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
      {
        id: 'created',
        header: '',
        size: 32,
        enableSorting: false,
        cell: ({ row }) => (
          <ManuallyCreatedIndicator
            sources={[
              {
                label: 'Variant',
                createdByUserId: row.original.created_by_user_id,
                createdBy: row.original.created_by,
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
        cell: ({ row }) => (
          <FlagIndicator paperId={paperId} flags={flags.byVariant.get(row.original.id) ?? []} />
        ),
      },
      {
        id: 'expander',
        size: 40,
        enableSorting: false,
        header: () => null,
        cell: ({ row }) => <RowExpander expanded={row.getIsExpanded()} onToggle={() => row.toggleExpanded()} />,
      },
      // The variant's own columns of the Occurrences table, drawn the same
      // way; the rest of that table's columns belong to an occurrence, which
      // a variant here does not have.
      {
        id: 'variant',
        header: 'Variant',
        accessorFn: (row) => row.variant_description,
        cell: ({ row }) => (
          <EntityLink
            onClick={() => row.toggleExpanded()}
            hoverContent={<VariantHoverCardContent variant={row.original} />}
          >
            <VariantLabel description={row.original.variant_description} hgvsP={row.original.hgvs_p} />
          </EntityLink>
        ),
      },
      {
        id: 'variant_type',
        header: 'Variant Type',
        accessorFn: (row) => row.variant_type,
        cell: ({ row }) => <EditableVariantTypeCell paperId={paperId} variant={row.original} />,
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
    [paperId, deleteMutation, flags],
  )

  return (
    <PipelineGate
      tasks={tasks}
      task={TaskType.PATIENT_VARIANT_OCCURRENCES}
      label="Individual/variant linking"
    >
      {variants.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Dna />
            </EmptyMedia>
            <EmptyTitle>Every extracted variant is linked to an individual</EmptyTitle>
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
            expandOnRowClick={false}
            reveal={reveal}
            renderSubComponent={({ row }) => (
              <VariantDetailPanel paperId={paperId} variant={row} />
            )}
          />
        </>
      )}
    </PipelineGate>
  )
}
