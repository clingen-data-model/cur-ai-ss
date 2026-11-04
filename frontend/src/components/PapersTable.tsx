/* Papers as rows, with the people who have worked on each.
 *
 * The genes table answers "what do we have on this gene"; this one answers
 * "what have I been working on", so the row is a paper and the columns are the
 * things you would scan down a list of your own work.
 */
import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import type { ExtractionTab } from '@/lib/extractionTabs'
import { DataTable } from '@/components/ui/data-table'
import { Collaborators } from '@/components/Collaborators'
import { StatusBadge } from '@/components/StatusBadge'
import { PaperProgressPopover } from '@/components/PaperProgressPopover'
import { ReviewStatusCell } from '@/components/ReviewStatusCell'
import { DeletePaperButton, RerunTaskButton } from '@/components/PaperActions'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { PaperSummaryResp } from '@/api/generated/types.gen'
import { ClipboardCheck, Flag } from 'lucide-react'

/** Midnight starting the local calendar day of `date`. */
function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

/** "Today 13:25", "Yesterday 09:02", "3 days ago", then the date once the
 * day stops being useful. The column sorts on the full timestamp, so the
 * two recent labels carry the local time: a day's papers would otherwise
 * read as one undifferentiated "Today" in an order the eye cannot check.
 * Days are local calendar days, not 24-hour windows: counted in windows,
 * yesterday 4 PM was "Today 4 PM" at 3 PM, a time still to come. */
function relativeTime(iso: string): string {
  const then = new Date(iso)
  const days = Math.round((startOfDay(new Date()) - startOfDay(then)) / 86_400_000)
  const time = then.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  if (days < 1) return `Today ${time}`
  if (days === 1) return `Yesterday ${time}`
  if (days < 30) return `${days} days ago`
  return then.toLocaleDateString()
}

/** The full local timestamp, for the tooltip on every row. */
function fullTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

/** A count that opens the tab listing what it counts. Zero is a dash,
 * since there is nothing on that tab to open. */
function CountLink({
  paperId,
  tab,
  count,
  className,
  icon,
}: {
  paperId: number
  tab: ExtractionTab
  count: number | undefined
  className?: string
  icon?: React.ReactNode
}) {
  if (!count) return <span className="text-muted-foreground">—</span>
  return (
    <Link
      to="/papers/$paperId/extraction"
      params={{ paperId: String(paperId) }}
      search={tab === 'occurrences' ? {} : { tab }}
      className={`inline-flex items-center gap-1 hover:underline underline-offset-4 ${className ?? ''}`}
    >
      {icon}
      {count}
    </Link>
  )
}

export function PapersTable({ papers }: { papers: PaperSummaryResp[] }) {
  const columns: ColumnDef<PaperSummaryResp>[] = useMemo(
    () => [
      {
        accessorKey: 'title',
        header: 'Paper',
        cell: ({ row }) => {
          const label = row.original.title ?? row.original.filename
          return (
            // Capped and truncated: paper titles run to well over a hundred
            // characters and would otherwise push every other column off the
            // row. The tooltip is the only way to read the rest.
            <Tooltip>
              <TooltipTrigger
                render={
                  <Link
                    to="/papers/$paperId/extraction"
                    params={{ paperId: String(row.original.id) }}
                    className="block max-w-[28rem] truncate font-medium hover:underline underline-offset-4"
                  />
                }
              >
                {label}
              </TooltipTrigger>
              <TooltipContent className="max-w-sm">{label}</TooltipContent>
            </Tooltip>
          )
        },
      },
      {
        // A string accessor, so the table's filter box matches it like the title.
        accessorKey: 'pmid',
        header: 'PMID',
        cell: ({ getValue }) => {
          const pmid = getValue() as string | null | undefined
          if (!pmid) return <span className="text-muted-foreground">—</span>
          return (
            <a
              href={`https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(pmid)}/`}
              target="_blank"
              rel="noreferrer"
              className="whitespace-nowrap hover:underline underline-offset-4"
            >
              {pmid}
            </a>
          )
        },
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
        header: 'Extraction Status',
        cell: ({ row }) => (
          <PaperProgressPopover paper={row.original}>
            <StatusBadge status={row.original.status} />
          </PaperProgressPopover>
        ),
      },
      {
        accessorKey: 'review_status',
        header: 'Review Status',
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <ReviewStatusCell paper={row.original} />
            {/* Curator sign-off: rows confirmed over rows extracted. */}
            {row.original.signoff && (row.original.signoff.total ?? 0) > 0 && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Link
                      to="/papers/$paperId/review"
                      params={{ paperId: String(row.original.id) }}
                      className="text-xs text-muted-foreground tabular-nums hover:underline"
                    />
                  }
                >
                  {row.original.signoff.confirmed ?? 0}/{row.original.signoff.total ?? 0}
                </TooltipTrigger>
                <TooltipContent>Occurrences a curator has confirmed; opens Review Mode</TooltipContent>
              </Tooltip>
            )}
          </div>
        ),
      },
      // The three counts link into the tab that lists what was counted:
      // patients to Families, variants to Occurrences, flags to Flags.
      {
        accessorKey: 'patient_count',
        header: 'Patients',
        cell: ({ row, getValue }) => (
          <CountLink paperId={row.original.id} tab="families" count={getValue() as number | undefined} />
        ),
      },
      {
        accessorKey: 'variant_count',
        header: 'Variants',
        cell: ({ row, getValue }) => (
          <CountLink paperId={row.original.id} tab="occurrences" count={getValue() as number | undefined} />
        ),
      },
      {
        // Open curator flags: decisions an agent asked a human to look at that
        // nobody has yet. A paper with any is not reviewed, whatever its
        // review status says, so it sits next to the counts a reviewer scans.
        accessorKey: 'open_flag_count',
        header: 'Flags',
        cell: ({ row, getValue }) => (
          <CountLink
            paperId={row.original.id}
            tab="flags"
            count={getValue() as number | undefined}
            className="text-violet-700 dark:text-violet-400"
            icon={<Flag className="size-3.5" />}
          />
        ),
      },
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
          <Tooltip>
            <TooltipTrigger render={<span className="text-muted-foreground whitespace-nowrap cursor-help" />}>
              {relativeTime(getValue() as string)}
            </TooltipTrigger>
            <TooltipContent>{fullTime(getValue() as string)}</TooltipContent>
          </Tooltip>
        ),
      },
      {
        id: 'actions',
        size: 108,
        enableSorting: false,
        header: () => null,
        // The same two controls the paper cards carry, so the action is in the
        // same place whichever view you reached the paper from, plus the way
        // into Review Mode, which is where a curator goes from this list.
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Tooltip>
              <TooltipTrigger
                render={
                  <Link
                    to="/papers/$paperId/review"
                    params={{ paperId: String(row.original.id) }}
                    aria-label="Review Mode"
                    className="flex items-center justify-center size-7 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  />
                }
              >
                <ClipboardCheck className="size-4" />
              </TooltipTrigger>
              <TooltipContent>Review Mode: walk the paper's families and confirm their occurrences</TooltipContent>
            </Tooltip>
            <RerunTaskButton paper={row.original} />
            <DeletePaperButton paper={row.original} />
          </div>
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
