/* Every curator flag on the paper in one list -- the home for flags about
 * things that were not extracted, which have no row to sit on, and the place
 * to review the rest in one pass. Each row names the agent, what the flag is
 * about (resolved to the row's own label when it has one), the subject and
 * reasoning, and the resolution or a Resolve button. Open flags come first.
 */
import { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { useQuery } from '@tanstack/react-query'
import { Flag, RefreshCw } from 'lucide-react'
import { getFamiliesPapersPaperIdFamiliesGet } from '@/api/generated'
import type { FlagResp, PatientResp, VariantResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Spinner } from '@/components/ui/spinner'
import { EvidencePopover } from '@/components/EvidencePopover'
import { ResolveFlagDialog } from '@/components/ResolveFlagDialog'
import { RerunFromFlagDialog } from '@/components/RerunFromFlagDialog'
import { usePaperFlags, useRerunFromFlag, useResolveFlag } from '@/hooks/usePaperFlags'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { flagSourceLabel, sortFlags } from '@/lib/flags'

const STALE_TIME = 5 * 60 * 1000

type Filter = 'open' | 'resolved' | 'all'

export function FlagsTab({
  paperId,
  patients,
  variants,
  rows: occurrenceRows,
}: {
  paperId: number
  patients: PatientResp[]
  variants: VariantResp[]
  rows: OccurrenceRow[]
}) {
  const flags = usePaperFlags(paperId)
  const resolve = useResolveFlag(paperId)
  const rerun = useRerunFromFlag(paperId)
  const [filter, setFilter] = useState<Filter>('open')
  const [resolving, setResolving] = useState<FlagResp | null>(null)
  const [rerunning, setRerunning] = useState<FlagResp | null>(null)

  // Families are not part of the page's shared queries; one small request
  // so a family-level flag can be named rather than numbered.
  const familiesQuery = useQuery({
    queryKey: ['families', paperId],
    queryFn: () => getFamiliesPapersPaperIdFamiliesGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const patientsById = useMemo(() => new Map(patients.map((p) => [p.id, p.identifier])), [patients])
  const variantsById = useMemo(() => new Map(variants.map((v) => [v.id, v.variant_description])), [variants])
  const variantByOccurrence = useMemo(
    () => new Map(occurrenceRows.map((r) => [r.occurrence.id, r.variant.variant_description])),
    [occurrenceRows],
  )
  const familiesById = useMemo(
    () => new Map((familiesQuery.data ?? []).map((f) => [f.id, f.identifier])),
    [familiesQuery.data],
  )

  /** What the flag is about, from the rows it links: "Patient 3 · c.123A>G"
   * for an occurrence, "Patient 3 · c.123A>G + c.456G>T" for a compound-het
   * pair, "Family 2" for a family, nothing for a flag about something not
   * extracted. A phenotype is named by its patient; the concept is in the
   * subject already. */
  const aboutLabel = (flag: FlagResp): string => {
    const variant =
      flag.variant_id != null ? (variantsById.get(flag.variant_id) ?? `Variant #${flag.variant_id}`) : null
    const partner =
      flag.paired_occurrence_id != null
        ? (variantByOccurrence.get(flag.paired_occurrence_id) ?? `Occurrence #${flag.paired_occurrence_id}`)
        : null
    const parts = [
      flag.family_id != null && (familiesById.get(flag.family_id) ?? `Family #${flag.family_id}`),
      flag.patient_id != null && (patientsById.get(flag.patient_id) ?? `Patient #${flag.patient_id}`),
      variant && partner ? `${variant} + ${partner}` : variant,
    ].filter((p): p is string => typeof p === 'string')
    return parts.join(' · ')
  }

  const rows = useMemo(() => {
    const picked =
      filter === 'open' ? flags.open : filter === 'resolved' ? flags.all.filter((f) => f.resolved_at != null) : flags.all
    return sortFlags(picked)
  }, [flags.all, flags.open, filter])

  const columns: ColumnDef<FlagResp>[] = useMemo(
    () => [
      {
        id: 'status',
        header: '',
        size: 28,
        enableSorting: false,
        cell: ({ row }) => (
          <Flag
            className={`size-3.5 ${row.original.resolved_at == null ? 'text-violet-600' : 'text-muted-foreground'}`}
          />
        ),
      },
      {
        id: 'source',
        header: 'Agent',
        accessorFn: (row) => flagSourceLabel(row),
        cell: ({ getValue }) => <span className="whitespace-nowrap text-muted-foreground">{getValue() as string}</span>,
      },
      {
        id: 'about',
        header: 'About',
        accessorFn: (row) => aboutLabel(row),
        cell: ({ getValue }) => {
          const label = getValue() as string
          return label ? (
            <span className="font-medium">{label}</span>
          ) : (
            <Badge variant="outline" className="font-normal">
              Not extracted
            </Badge>
          )
        },
      },
      {
        id: 'subject',
        header: 'Flag',
        accessorFn: (row) => `${row.subject} ${row.evidence.reasoning ?? ''}`,
        cell: ({ row }) => (
          <div className="flex items-start gap-1 max-w-xl">
            <div className="min-w-0">
              <p className="font-medium break-words">{row.original.subject}</p>
              {row.original.evidence.reasoning && (
                <p className="text-xs text-muted-foreground break-words">{row.original.evidence.reasoning}</p>
              )}
            </div>
            <EvidencePopover block={row.original.evidence} />
          </div>
        ),
      },
      {
        id: 'resolution',
        header: 'Resolution',
        accessorFn: (row) => row.resolution_note ?? '',
        cell: ({ row }) => {
          const flag = row.original
          if (flag.resolved_at == null) {
            return (
              <div className="flex items-center gap-1">
                <Button size="sm" variant="outline" onClick={() => setResolving(flag)}>
                  Resolve
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setRerunning(flag)} title="Re-run the agent">
                  <RefreshCw className="size-3.5" />
                </Button>
              </div>
            )
          }
          return (
            <div className="max-w-xs">
              <p className="text-sm break-words">{flag.resolution_note || 'Resolved without a note'}</p>
              <p className="text-xs text-muted-foreground">
                {flag.resolved_by?.name ?? 'Unknown'}
                {flag.resolved_at ? `, ${new Date(flag.resolved_at).toLocaleDateString()}` : ''}
              </p>
            </div>
          )
        },
      },
    ],
    // aboutLabel reads the three id->label maps; listing them keeps the
    // column fresh when a rename or a late families response lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [patientsById, variantsById, familiesById, variantByOccurrence],
  )

  if (flags.isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  if (flags.all.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Flag />
          </EmptyMedia>
          <EmptyTitle>No flags</EmptyTitle>
          <EmptyDescription>
            No agent raised a decision for review on this paper. Flags appear once the agents have run on
            a prompt that asks for them.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const resolvedCount = flags.all.length - flags.open.length

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        {(
          [
            ['open', `Open (${flags.open.length})`],
            ['resolved', `Resolved (${resolvedCount})`],
            ['all', `All (${flags.all.length})`],
          ] as const
        ).map(([value, label]) => (
          <Button
            key={value}
            size="sm"
            variant={filter === value ? 'default' : 'ghost'}
            onClick={() => setFilter(value)}
          >
            {label}
          </Button>
        ))}
      </div>
      <DataTable
        columns={columns}
        data={rows}
        filterPlaceholder="Filter flags..."
        getRowId={(row) => String(row.id)}
      />
      <ResolveFlagDialog
        flag={resolving}
        open={resolving !== null}
        onOpenChange={(open) => {
          if (!open) setResolving(null)
        }}
        isPending={resolve.isPending}
        onConfirm={(note) => {
          if (!resolving) return
          resolve.mutate({ flagId: resolving.id, note }, { onSuccess: () => setResolving(null) })
        }}
      />
      <RerunFromFlagDialog
        paperId={paperId}
        flag={rerunning}
        open={rerunning !== null}
        onOpenChange={(open) => {
          if (!open) setRerunning(null)
        }}
        isPending={rerun.isPending}
        onConfirm={(note) => {
          if (!rerunning) return
          rerun.mutate({ flagId: rerunning.id, note }, { onSuccess: () => setRerunning(null) })
        }}
      />
    </div>
  )
}
