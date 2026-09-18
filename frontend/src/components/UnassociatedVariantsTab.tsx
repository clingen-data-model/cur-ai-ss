/* Variants extracted from the paper that no occurrence links to a patient
 * yet -- either linking hasn't run, or it found nothing to link them to. */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import type { VariantResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'

export function UnassociatedVariantsTab({
  paperId,
  variants,
}: {
  paperId: number
  variants: VariantResp[]
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

  if (variants.length === 0) {
    return <p className="text-sm text-muted-foreground">Every extracted variant is linked to a patient.</p>
  }

  return (
    <DataTable
      columns={columns}
      data={variants}
      filterPlaceholder="Filter variants..."
      getRowId={(row) => String(row.id)}
      getRowCanExpand={() => true}
      renderSubComponent={({ row }) => <VariantDetailPanel paperId={paperId} variant={row} />}
    />
  )
}
