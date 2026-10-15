/* Every curator flag on the paper in one list -- the home for flags about
 * things that were not extracted, which have no row to sit on, and the place
 * to review the rest in one pass. Each row names the agent, what the flag is
 * about (the linked rows, each a link to its tab), the subject and reasoning,
 * and the resolution or Resolve / Re-run buttons. Open flags come first.
 */
import { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { useQuery } from '@tanstack/react-query'
import { CheckCheck, Dna, Flag, Info, RefreshCw, User, Users } from 'lucide-react'
import { getFamiliesPapersPaperIdFamiliesGet } from '@/api/generated'
import type { FlagResp, PatientResp, VariantResp } from '@/api/generated/types.gen'
import { DataTable } from '@/components/ui/data-table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { EvidencePopover } from '@/components/EvidencePopover'
import { ResolveAllFlagsDialog } from '@/components/ResolveAllFlagsDialog'
import { ResolveFlagDialog } from '@/components/ResolveFlagDialog'
import { RerunFromFlagDialog } from '@/components/RerunFromFlagDialog'
import { usePaperFlags, useRerunFromFlag, useResolveFlag, useResolveFlags } from '@/hooks/usePaperFlags'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { flagSourceLabel, sortFlags } from '@/lib/flags'
import type { FlagTarget } from '@/lib/flagTarget'

const STALE_TIME = 5 * 60 * 1000
const ANY_AGENT = 'any'

type Filter = 'open' | 'resolved' | 'all'

/** One linked row, as a chip that opens it. */
function AboutChip({
  kind,
  label,
  onClick,
}: {
  kind: 'family' | 'patient' | 'variant' | 'phenotype'
  label: string
  onClick?: () => void
}) {
  const Icon = kind === 'family' ? Users : kind === 'patient' ? User : kind === 'variant' ? Dna : Flag
  const inner = (
    <>
      <Icon className="size-3 shrink-0 text-muted-foreground" />
      <span className="truncate">{label}</span>
    </>
  )
  const className =
    'inline-flex max-w-56 items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium'
  return onClick ? (
    <button
      type="button"
      className={`${className} hover:bg-muted hover:underline underline-offset-2 cursor-pointer`}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      title={`Open ${kind}`}
    >
      {inner}
    </button>
  ) : (
    <span className={className}>{inner}</span>
  )
}

export function FlagsTab({
  paperId,
  patients,
  variants,
  rows: occurrenceRows,
  onNavigate,
}: {
  paperId: number
  patients: PatientResp[]
  variants: VariantResp[]
  rows: OccurrenceRow[]
  /** Open the tab and row a flag's About chip names. */
  onNavigate?: (target: FlagTarget) => void
}) {
  const flags = usePaperFlags(paperId)
  const resolve = useResolveFlag(paperId)
  const resolveAll = useResolveFlags(paperId)
  const rerun = useRerunFromFlag(paperId)
  const [filter, setFilter] = useState<Filter>('open')
  const [agent, setAgent] = useState<string>(ANY_AGENT)
  const [resolving, setResolving] = useState<FlagResp | null>(null)
  const [resolvingAll, setResolvingAll] = useState(false)
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

  /** The agents that raised anything on this paper, for the dropdown. */
  const agents = useMemo(() => {
    const seen = new Map<string, string>()
    for (const flag of flags.all) seen.set(flag.source, flagSourceLabel(flag))
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [flags.all])

  /** Plain-text form of the About column, for sorting and the filter box:
   * "F2 · F3 II-1 · c.1738 G>A", "c.1A>G + c.2C>T" for a pair, empty for
   * a flag about something not extracted. */
  const aboutText = (flag: FlagResp): string => {
    const variant =
      flag.variant_id != null ? (variantsById.get(flag.variant_id) ?? `Variant #${flag.variant_id}`) : null
    const partner =
      flag.paired_occurrence_id != null
        ? (variantByOccurrence.get(flag.paired_occurrence_id) ?? `Occurrence #${flag.paired_occurrence_id}`)
        : null
    return [
      flag.family_id != null && (familiesById.get(flag.family_id) ?? `Family #${flag.family_id}`),
      flag.patient_id != null && (patientsById.get(flag.patient_id) ?? `Patient #${flag.patient_id}`),
      variant && partner ? `${variant} + ${partner}` : variant,
      flag.phenotype_id != null && 'phenotype',
    ]
      .filter((p): p is string => typeof p === 'string')
      .join(' · ')
  }

  // The two filters cross: the state buttons count within the chosen
  // agent, and the dropdown counts within the chosen state, so each
  // control says what picking it would show.
  const resolved = useMemo(() => flags.all.filter((f) => f.resolved_at != null), [flags.all])
  const byState = filter === 'open' ? flags.open : filter === 'resolved' ? resolved : flags.all
  const byAgent = useMemo(
    () => (agent === ANY_AGENT ? flags.all : flags.all.filter((f) => f.source === agent)),
    [flags.all, agent],
  )
  const agentCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const flag of byState) counts.set(flag.source, (counts.get(flag.source) ?? 0) + 1)
    return counts
  }, [byState])
  const rows = useMemo(
    () => sortFlags(agent === ANY_AGENT ? byState : byState.filter((f) => f.source === agent)),
    [byState, agent],
  )

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
        header: () => (
          <span className="inline-flex items-center gap-1">
            About
            <Tooltip>
              <TooltipTrigger render={<span />}>
                <Info className="size-3.5 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                The extracted rows the flag concerns: a family, a patient, a variant, a patient-variant link
                (both halves of a compound-het pair), or a phenotype. Click one to open it. "Not extracted"
                means the flag is about something the agent left out, so there is no row.
              </TooltipContent>
            </Tooltip>
          </span>
        ),
        accessorFn: (row) => aboutText(row),
        cell: ({ row }) => {
          const flag = row.original
          const go = (target: FlagTarget) => onNavigate?.(target)
          const linkTarget: FlagTarget | null =
            flag.occurrence_id != null ? { kind: 'occurrence', id: flag.occurrence_id } : null
          const chips: React.ReactNode[] = []
          if (flag.family_id != null) {
            const id = flag.family_id
            chips.push(
              <AboutChip
                key="family"
                kind="family"
                label={familiesById.get(id) ?? `Family #${id}`}
                onClick={onNavigate && (() => go({ kind: 'family', id }))}
              />,
            )
          }
          if (flag.patient_id != null) {
            const id = flag.patient_id
            chips.push(
              <AboutChip
                key="patient"
                kind="patient"
                label={patientsById.get(id) ?? `Patient #${id}`}
                onClick={onNavigate && (() => go(linkTarget ?? { kind: 'patient', id }))}
              />,
            )
          }
          if (flag.variant_id != null) {
            const id = flag.variant_id
            chips.push(
              <AboutChip
                key="variant"
                kind="variant"
                label={variantsById.get(id) ?? `Variant #${id}`}
                onClick={onNavigate && (() => go(linkTarget ?? { kind: 'variant', id }))}
              />,
            )
          }
          if (flag.paired_occurrence_id != null) {
            const id = flag.paired_occurrence_id
            chips.push(
              <AboutChip
                key="pair"
                kind="variant"
                label={`+ ${variantByOccurrence.get(id) ?? `Occurrence #${id}`}`}
                onClick={onNavigate && (() => go({ kind: 'occurrence', id }))}
              />,
            )
          }
          if (flag.phenotype_id != null && flag.patient_id != null) {
            const patientId = flag.patient_id
            chips.push(
              <AboutChip
                key="phenotype"
                kind="phenotype"
                label="phenotype"
                onClick={onNavigate && (() => go({ kind: 'patient', id: patientId }))}
              />,
            )
          }
          return chips.length ? (
            <div className="flex flex-wrap items-center gap-1 whitespace-normal">{chips}</div>
          ) : (
            <Badge variant="outline" className="font-normal text-muted-foreground">
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
          <div className="flex items-start gap-1 max-w-xl whitespace-normal">
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
            <div className="max-w-xs whitespace-normal">
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
    // aboutText and the chips read the id->label maps; listing them keeps
    // the column fresh when a rename or a late families response lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [patientsById, variantsById, familiesById, variantByOccurrence, onNavigate],
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

  const openCount = byAgent.filter((f) => f.resolved_at == null).length

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        {(
          [
            ['open', `Open (${openCount})`],
            ['resolved', `Resolved (${byAgent.length - openCount})`],
            ['all', `All (${byAgent.length})`],
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
        <div className="ml-auto flex items-center gap-2">
          {filter === 'open' && rows.length > 0 && (
            <Button size="sm" variant="outline" onClick={() => setResolvingAll(true)}>
              <CheckCheck className="size-3.5 mr-1.5" />
              Resolve all ({rows.length})
            </Button>
          )}
          <label className="text-sm text-muted-foreground whitespace-nowrap">Agent</label>
          <Select value={agent} onValueChange={(next: string | null) => setAgent(next ?? ANY_AGENT)}>
            <SelectTrigger className="w-56">
              <SelectValue>
                {(value: string | null) =>
                  value === null || value === ANY_AGENT
                    ? `Any (${byState.length})`
                    : `${agents.find(([s]) => s === value)?.[1] ?? value} (${agentCounts.get(value) ?? 0})`
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY_AGENT}>Any ({byState.length})</SelectItem>
              {agents.map(([source, label]) => (
                <SelectItem key={source} value={source}>
                  {label} ({agentCounts.get(source) ?? 0})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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
      <ResolveAllFlagsDialog
        count={rows.length}
        agentLabel={agent === ANY_AGENT ? null : (agents.find(([s]) => s === agent)?.[1] ?? agent)}
        open={resolvingAll}
        onOpenChange={setResolvingAll}
        isPending={resolveAll.isPending}
        onConfirm={(note) => {
          resolveAll.mutate(
            { flagIds: rows.map((f) => f.id), note },
            { onSuccess: () => setResolvingAll(false) },
          )
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
