/* The review walk: a paper's families one at a time, each beside the PDF
 * with its evidence highlighted, and one confirm per family.
 *
 * A case is a family -- its members, their occurrences and variants, and
 * the open flags about any of them -- in the paper's order (lib/misc/
 * review_cases.py); the variants linked to nobody and the flags about
 * nothing in particular trail as two more cases. The rail on the left
 * shows the current case the way the paper page shows the paper: the same
 * Occurrences table for its rows (flags, sign-off and evidence on each
 * row, the Patient and Variant panels behind the expander), the same
 * Unassociated tables for a member with no linked variant or a variant
 * linked to nobody, the family's row of the same Families table (its
 * detail, with the segregation analysis, behind the expander), then the
 * same Flags table for the case's
 * open flags, whose count the header carries. A case opens with every
 * citation it carries highlighted -- the members' fields, the occurrences',
 * the variants', the family's and its segregation evidence, the flags' --
 * derived from the data as it loads rather than set once on arrival, so a
 * slow query cannot leave the pane blank; clicking a field's label in a
 * panel narrows the highlight to that field until the next case or the
 * pane's "Highlight all case fields" (EditableField's FieldRow, in the provider's
 * inline mode), and every
 * "View in PDF" lands in the same pane instead of a sheet. The split is
 * draggable.
 *
 * Confirm stamps the case's occurrences (lib/models/signoff.py) and moves
 * to the next unconfirmed family. The two trailing cases are optional: the
 * walk never lands on them by itself, they are not in the progress count,
 * and a paper completes with them untouched (open flags included). Keys: arrows (or j/k) move, Enter
 * confirms, u takes a confirmation back.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, ChevronLeft, Flag, Highlighter, Undo2 } from 'lucide-react'
import {
  getFamiliesPapersPaperIdFamiliesGet,
  getSegregationAnalysisPapersPaperIdSegregationAnalysisGet,
} from '@/api/generated'
import { ReviewStatus } from '@/api/generated/types.gen'
import type { Citation, FlagResp, PatientResp, VariantResp } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { FamiliesTab } from '@/components/FamiliesTab'
import { FlagsTab } from '@/components/FlagsTab'
import { OccurrencesTab } from '@/components/OccurrencesTab'
import { EvidencePanes, PdfHighlightProvider, type HighlightTarget } from '@/components/PdfHighlightProvider'
import { ReviewStatusBadge } from '@/components/ReviewStatusCell'
import { UnassociatedPatientsTab } from '@/components/UnassociatedPatientsTab'
import { UnassociatedVariantsTab } from '@/components/UnassociatedVariantsTab'
import { usePaperFlags } from '@/hooks/usePaperFlags'
import { usePaperOccurrences } from '@/hooks/usePaperOccurrences'
import { caseRows, useReviewCases, useSignoff, type ReviewCaseResp } from '@/hooks/useSignoff'

const STALE_TIME = 5 * 60 * 1000

/** Every citation on an entity's evidence blocks -- any field holding a
 * block with citations, or a list of them: the `*_evidence` fields of a
 * patient, variant, occurrence or family, the segregation analysis's
 * extracted values, a flag's evidence -- deduplicated: what a case
 * highlights by default. */
function collectCitations(entities: unknown[]): Citation[] {
  const seen = new Set<string>()
  const found: Citation[] = []
  const take = (block: unknown) => {
    if (typeof block !== 'object' || block === null) return
    const citations = (block as { citations?: unknown }).citations
    if (!Array.isArray(citations)) return
    for (const citation of citations as Citation[]) {
      const key = `${citation.anchor}\u0000${citation.quote ?? ''}`
      if (seen.has(key)) continue
      seen.add(key)
      found.push(citation)
    }
  }
  for (const entity of entities) {
    if (typeof entity !== 'object' || entity === null) continue
    for (const value of Object.values(entity)) {
      if (Array.isArray(value)) value.forEach(take)
      else take(value)
    }
  }
  return found
}

/** A case the confirm button can stamp: a family with at least one
 * occurrence. The others have nothing to stamp, only flags to resolve. */
function isStampable(reviewCase: ReviewCaseResp): boolean {
  return reviewCase.kind === 'family' && (reviewCase.occurrence_ids?.length ?? 0) > 0
}

function openFlagCount(reviewCase: ReviewCaseResp): number {
  return reviewCase.flag_ids?.length ?? 0
}

/** True while the key press should go to a control, not the walk. */
function typingOrDialog(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [contenteditable="true"], [role="dialog"], [role="alertdialog"]')) {
    return true
  }
  return document.querySelector('[role="dialog"], [role="alertdialog"]') !== null
}

export function ReviewPage() {
  const params = useParams({ from: '/papers/$paperId/review' })
  const paperId = parseInt(params.paperId, 10)
  const search = useSearch({ from: '/papers/$paperId/review' })
  const navigate = useNavigate({ from: '/papers/$paperId/review' })

  const { paper, rows, allPatients, allVariants, isLoading, isError, error } = usePaperOccurrences(paperId)
  const flags = usePaperFlags(paperId)
  const familiesQuery = useQuery({
    queryKey: ['families', paperId],
    queryFn: () => getFamiliesPapersPaperIdFamiliesGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })
  const segregationQuery = useQuery({
    queryKey: ['segregation-analysis', paperId],
    queryFn: () => getSegregationAnalysisPapersPaperIdSegregationAnalysisGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })
  const casesQuery = useReviewCases(paperId)
  const signoff = useSignoff(paperId)
  // A field's label narrows the pane to that field; null is the case's
  // default highlight, everything it cites.
  const [narrowed, setNarrowed] = useState<HighlightTarget | null>(null)

  const cases = useMemo(() => casesQuery.data ?? [], [casesQuery.data])
  const currentIndex = useMemo(() => {
    const asked = search.case ? cases.findIndex((c) => c.key === search.case) : -1
    if (asked !== -1) return asked
    const firstOpen = cases.findIndex((c) => !c.confirmed && !c.optional)
    return firstOpen === -1 ? 0 : firstOpen
  }, [cases, search.case])
  const current: ReviewCaseResp | undefined = cases[currentIndex]

  const goTo = useCallback((key: string) => void navigate({ search: { case: key }, replace: true }), [navigate])
  const step = useCallback(
    (direction: 1 | -1) => {
      const next = cases[currentIndex + direction]
      if (next) goTo(next.key)
    },
    [cases, currentIndex, goTo],
  )
  /** The next unconfirmed required case after this one, wrapping, or none. */
  const nextOpen = useMemo(() => {
    for (let offset = 1; offset <= cases.length; offset++) {
      const candidate = cases[(currentIndex + offset) % cases.length]
      if (candidate && !candidate.confirmed && !candidate.optional && candidate.key !== current?.key) return candidate
    }
    return undefined
  }, [cases, currentIndex, current?.key])

  const patientsById = useMemo(() => new Map(allPatients.map((p) => [p.id, p])), [allPatients])
  const variantsById = useMemo(() => new Map(allVariants.map((v) => [v.id, v])), [allVariants])
  const flagsById = useMemo(() => new Map(flags.all.map((f) => [f.id, f])), [flags.all])
  const casePatients = useMemo(
    () => (current?.patient_ids ?? []).map((id) => patientsById.get(id)).filter((p): p is PatientResp => !!p),
    [current, patientsById],
  )
  const caseVariants = useMemo(
    () => (current?.variant_ids ?? []).map((id) => variantsById.get(id)).filter((v): v is VariantResp => !!v),
    [current, variantsById],
  )
  // The case's rows of the Occurrences table, in the table's own order.
  const caseOccurrenceRows = useMemo(() => {
    const wanted = new Set(current?.occurrence_ids ?? [])
    return rows.filter((row) => wanted.has(row.occurrence.id))
  }, [current, rows])
  // A member that no occurrence links: shown as the Unassociated Patients
  // tab shows them.
  const caseUnlinkedPatients = useMemo(() => {
    const linked = new Set(caseOccurrenceRows.map((row) => row.patient.id))
    return casePatients.filter((patient) => !linked.has(patient.id))
  }, [casePatients, caseOccurrenceRows])
  const caseFlagIds = useMemo(() => new Set(current?.flag_ids ?? []), [current])
  const caseFlags = useMemo(
    () => [...caseFlagIds].map((id) => flagsById.get(id)).filter((f): f is FlagResp => !!f),
    [caseFlagIds, flagsById],
  )
  const family = useMemo(
    () => (current?.family_id != null ? familiesQuery.data?.find((f) => f.id === current.family_id) : undefined),
    [current, familiesQuery.data],
  )
  const familyIds = useMemo(() => new Set(current?.family_ids ?? []), [current])
  const segregation = useMemo(
    () => (current?.family_id != null ? segregationQuery.data?.find((s) => s.family_id === current.family_id) : undefined),
    [current, segregationQuery.data],
  )

  const defaultTarget = useMemo<HighlightTarget | null>(() => {
    if (!current) return null
    const citations = collectCitations([
      ...casePatients,
      ...caseOccurrenceRows.map((row) => row.occurrence),
      ...caseVariants,
      ...(family ? [family] : []),
      ...(segregation ? [segregation] : []),
      ...caseFlags.map((flag) => ({ evidence: flag.evidence })),
    ])
    return citations.length > 0 ? { citations } : null
  }, [current, casePatients, caseOccurrenceRows, caseVariants, family, segregation, caseFlags])
  // A new case drops the narrowing; a save that refreshes a row does not.
  useEffect(() => setNarrowed(null), [current?.key])
  const target = narrowed ?? defaultTarget

  const confirmCurrent = useCallback(() => {
    if (!current || !isStampable(current) || signoff.isPending) return
    signoff.mutate({ ...caseRows(current), confirmed: true }, { onSuccess: () => nextOpen && goTo(nextOpen.key) })
  }, [current, signoff, nextOpen, goTo])
  const unconfirmCurrent = useCallback(() => {
    if (!current || !isStampable(current) || !current.confirmed || signoff.isPending) return
    signoff.mutate({ ...caseRows(current), confirmed: false })
  }, [current, signoff])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || typingOrDialog(event)) return
      if (event.key === 'ArrowRight' || event.key === 'j') {
        event.preventDefault()
        step(1)
      } else if (event.key === 'ArrowLeft' || event.key === 'k') {
        event.preventDefault()
        step(-1)
      } else if (event.key === 'Enter') {
        event.preventDefault()
        confirmCurrent()
      } else if (event.key === 'u') {
        event.preventDefault()
        unconfirmCurrent()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [step, confirmCurrent, unconfirmCurrent])

  if (isLoading || casesQuery.isPending) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner />
      </div>
    )
  }
  if (isError || casesQuery.isError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-red-500">Error loading paper: {(error ?? casesQuery.error)?.message ?? 'Unknown error'}</div>
      </div>
    )
  }

  const tasks = paper?.tasks ?? []
  const required = cases.filter((c) => !c.optional)
  const confirmedCases = required.filter((c) => c.confirmed).length
  const progress = { total: paper?.signoff?.total ?? 0, confirmed: paper?.signoff?.confirmed ?? 0 }
  const reviewStatus = paper?.review_status ?? ReviewStatus.NOT_ASSIGNED
  const openFlags = current ? openFlagCount(current) : 0

  return (
    <PdfHighlightProvider paperId={paperId} pdfUrl={paper?.pdf_url} filename={paper?.filename} inline={setNarrowed}>
      {/* Full-bleed: the walk wants the viewport, not main's padding. */}
      <div className="-mx-6 -my-8 h-[calc(100vh-3.25rem)]">
        <ResizablePanelGroup orientation="horizontal" className="h-full">
          <ResizablePanel defaultSize={55} minSize={30} className="flex flex-col bg-muted/20">
            <div className="border-b bg-background px-4 py-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Link
                  to="/papers/$paperId/extraction"
                  params={{ paperId: String(paperId) }}
                  className="text-sm text-muted-foreground hover:underline flex items-center gap-1 min-w-0"
                >
                  <ArrowLeft className="size-3.5 shrink-0" />
                  <span className="truncate">{paper?.title ?? paper?.filename}</span>
                </Link>
                <ReviewStatusBadge status={reviewStatus} assignee={paper?.review_assignee} />
              </div>
              <div className="flex items-center gap-2">
                <Select value={current?.key ?? ''} onValueChange={(key) => key && goTo(String(key))}>
                  <SelectTrigger size="sm" className="flex-1 min-w-0">
                    <SelectValue placeholder="No cases yet" />
                  </SelectTrigger>
                  <SelectContent>
                    {cases.map((c, index) => (
                      <SelectItem key={c.key} value={c.key}>
                        {index + 1}. {c.label}
                        {c.optional ? ' (optional)' : c.confirmed ? ' ✓' : openFlagCount(c) > 0 ? ` ⚑${openFlagCount(c)}` : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={() => step(-1)} disabled={currentIndex <= 0} title="Previous case (←)">
                  <ChevronLeft className="size-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => step(1)}
                  disabled={currentIndex >= cases.length - 1}
                  title="Next case (→)"
                >
                  <ArrowRight className="size-4" />
                </Button>
              </div>
              <div className="text-xs text-muted-foreground">
                Case {cases.length ? currentIndex + 1 : 0} of {cases.length} · {confirmedCases}/{required.length} families
                confirmed · {progress.confirmed}/{progress.total} occurrences
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
              {!current ? (
                <p className="text-sm text-muted-foreground">
                  Nothing to review yet: the pipeline has not produced patients or variants for this paper.
                </p>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-semibold truncate">{current.label}</h2>
                      {current.optional && <Badge variant="secondary">Optional</Badge>}
                      {openFlags > 0 ? (
                        <Badge variant="outline" className="border-violet-500 text-violet-700 dark:text-violet-400">
                          <Flag className="size-3" />
                          {openFlags} open flag{openFlags === 1 ? '' : 's'}
                        </Badge>
                      ) : (
                        <Badge variant="secondary">No open flags</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {current.confirmed ? (
                        <Button variant="outline" size="sm" onClick={unconfirmCurrent} disabled={signoff.isPending} title="Take back (u)">
                          <Undo2 className="size-3.5 mr-1" />
                          Confirmed
                        </Button>
                      ) : isStampable(current) ? (
                        <Button size="sm" onClick={confirmCurrent} disabled={signoff.isPending} title="Confirm this case (Enter)">
                          <Check className="size-3.5 mr-1" />
                          Confirm case
                        </Button>
                      ) : current.kind === 'family' ? (
                        <span className="text-xs text-muted-foreground">No occurrence to confirm</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">Nothing to confirm here</span>
                      )}
                    </div>
                  </div>

                  {current.kind === 'family' && caseOccurrenceRows.length > 0 && (
                    <OccurrencesTab paperId={paperId} rows={caseOccurrenceRows} flags={flags} />
                  )}

                  {current.kind === 'family' && caseUnlinkedPatients.length > 0 && (
                    <section className="space-y-1">
                      <h3 className="text-sm font-semibold">
                        {caseOccurrenceRows.length > 0 ? 'Members with no linked variant' : 'Members'}
                      </h3>
                      <UnassociatedPatientsTab
                        paperId={paperId}
                        patients={caseUnlinkedPatients}
                        allPatients={allPatients}
                        tasks={tasks}
                        flags={flags}
                      />
                    </section>
                  )}

                  {current.kind === 'unlinked_variants' && (
                    <UnassociatedVariantsTab paperId={paperId} variants={caseVariants} tasks={tasks} flags={flags} />
                  )}

                  {current.kind === 'family' && (
                    <section className="space-y-1">
                      <h3 className="text-sm font-semibold">Family</h3>
                      <FamiliesTab paperId={paperId} only={familyIds} />
                    </section>
                  )}

                  {(openFlags > 0 || current.kind === 'paper') && (
                    <section className="space-y-1">
                      <h3 className="text-sm font-semibold">Flags</h3>
                      <FlagsTab
                        paperId={paperId}
                        patients={allPatients}
                        variants={allVariants}
                        rows={rows}
                        only={caseFlagIds}
                      />
                    </section>
                  )}
                </>
              )}
            </div>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={45} minSize={25} className="flex flex-col">
            <EvidencePanes
              paperId={paperId}
              pdfUrl={paper?.pdf_url}
              filename={paper?.filename}
              target={target}
              toolbar={
                narrowed ? (
                  <Button variant="outline" size="sm" onClick={() => setNarrowed(null)} title="Back to every field of this case">
                    <Highlighter className="size-3.5 mr-1" />
                    Highlight all case fields
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground">
                    {defaultTarget ? 'Every field of this case' : 'Nothing cited'}
                  </span>
                )
              }
            />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </PdfHighlightProvider>
  )
}
