/* Papers as rows, with the people who have worked on each.
 *
 * The genes table answers "what do we have on this gene"; this one answers
 * "what have I been working on", so the row is a paper and the columns are the
 * things you would scan down a list of your own work.
 */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { DataTable } from '@/components/ui/data-table'
import { Collaborators } from '@/components/Collaborators'
import { StatusBadge } from '@/components/StatusBadge'
import type { PaperSummaryResp } from '@/api/generated/types.gen'

/** "3 days ago" from an ISO timestamp; absolute once it stops being useful. */
function relativeTime(iso: string): string {
  const then = new Date(iso)
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000)
  if (days < 1) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days} days ago`
  return then.toLocaleDateString()
}

export function PapersTable({ papers }: { papers: PaperSummaryResp[] }) {
  const columns: ColumnDef<PaperSummaryResp>[] = useMemo(
    () => [
      {
        accessorKey: 'title',
        header: 'Paper',
        cell: ({ row }) => (
          <Link
            to="/papers/$paperId/patients"
            params={{ paperId: String(row.original.id) }}
            className="font-medium hover:underline underline-offset-4"
          >
            {row.original.title ?? row.original.filename}
          </Link>
        ),
      },
      {
        accessorKey: 'gene_symbol',
        header: 'Gene',
        cell: ({ getValue }) => (
          <span className="font-medium">{getValue() as string}</span>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      { accessorKey: 'patient_count', header: 'Patients' },
      { accessorKey: 'variant_count', header: 'Variants' },
      {
        id: 'collaborators',
        header: 'Worked on by',
        // Sorting an avatar group has no meaning a reader would predict.
        enableSorting: false,
        cell: ({ row }) => (
          <Collaborators users={row.original.collaborators ?? []} />
        ),
      },
      {
        accessorKey: 'updated_at',
        header: 'Updated',
        cell: ({ getValue }) => (
          <span className="text-muted-foreground whitespace-nowrap">
            {relativeTime(getValue() as string)}
          </span>
        ),
      },
    ],
    [],
  )

  return (
    <DataTable
      columns={columns}
      data={papers}
      filterPlaceholder="Filter papers..."
    />
  )
}
