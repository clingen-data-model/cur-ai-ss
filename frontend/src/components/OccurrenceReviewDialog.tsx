/* The occurrence review: the paper's individual-variant occurrences, one at a
 * time, beside the PDF, which highlights the field in focus. It
 * replaced Review Mode (a page that walked the paper a family at a time with
 * the paper page's tables) on 2026-11-19: curators found checking a family's
 * rows in tables, a popover per field, slower than the HPO review's one
 * record on screen with its evidence and the keyboard to move on.
 *
 *   j / k  previous / next field: the occurrence's, then the individual's,
 *          then the variant's, in the order the pane shows them; past the
 *          last, on to the next occurrence, and back past the first, to the
 *          occurrence as a whole. A field in focus is outlined, glides to the
 *          top of the pane, and the PDF highlights what it cites alone.
 *   J / K  previous / next occurrence
 *   a      accept: stamp the occurrence as reviewed (lib/models/signoff.py)
 *          and go to the next unreviewed one; on an accepted one, take it back
 *   x      reject: delete the occurrence, as the table's delete does; only
 *          with the occurrence as a whole in focus, since a field cannot be
 *          rejected, only changed
 *   e      edit: with a field in focus, put the cursor in its control (Space
 *          then opens a dropdown); a read-only field has none
 *
 * A step is one occurrence, or a compound-het pair, which the occurrences
 * table already draws as one row: the individual once, then each variant
 * with its own fields, and accept or reject act on both. Every field is the
 * table's own editable control, with its required edit note; an edit leaves
 * the stamp as it is, and the agent rewrites that clear it are unchanged.
 *
 * Opening the review writes a snapshot ("Before occurrence review"), which
 * is how a rejection is undone: deletes are not reversible otherwise.
 *
 * Steps are grouped by family and listed in paper order: each step at the
 * first passage any of its occurrences' fields cites, each family at its
 * first step.
 *
 * The modal renders the PDF itself and wraps its body in an inline
 * PdfHighlightProvider, so a field's View in PDF highlights in this pane
 * rather than opening the paper page's sheet on top of the modal, as in the
 * HPO review. The occurrence as a whole highlights nothing: every field's
 * passages at once (the first version) lit up most of a page and pointed
 * at no one value. */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check, Circle } from 'lucide-react'
import {
  deleteOccurrencePapersPaperIdOccurrencesOccurrenceIdDelete,
  signoffRowsPapersPaperIdSignoffPost,
  startOccurrenceReviewPapersPaperIdOccurrencesReviewPost,
} from '@/api/generated'
import type { Citation, FlagResp, PatientVariantOccurrenceResp } from '@/api/generated/types.gen'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import {
  EvidencePanes,
  PdfHighlightProvider,
  usePdfHighlight,
  type HighlightTarget,
} from '@/components/PdfHighlightProvider'
import { EvidencePopover, ViewEvidenceButton, type EvidenceLike } from '@/components/EvidencePopover'
import {
  EditableDeNovoCell,
  EditableDiseaseNameCell,
  EditableInheritanceCell,
  EditableTestingMethodsCell,
  EditableZygosityCell,
  MondoDiseaseCell,
} from '@/components/OccurrenceEditableCells'
import { FlagCard } from '@/components/FlagIndicator'
import {
  ReviewSplit,
  KeyLegend,
  StepLabel,
  dialogAbove,
  useReviewKeys,
} from '@/components/ReviewParts'
import { VariantLabel } from '@/components/VariantLabel'
import { PedigreeSymbol } from '@/components/PedigreeSymbol'
import { hasSeveralFamilies } from '@/components/PatientIdCell'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'
import { VariantDetailPanel } from '@/components/VariantDetailPanel'
import type { FlagIndex } from '@/hooks/usePaperFlags'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { parseAnchor } from '@/lib/anchors'
import { apiErrorMessage } from '@/lib/apiError'
import { cn } from '@/lib/utils'

// The legend follows what is in focus: the occurrence as a whole can be
// rejected, a field can only be changed.
const OCCURRENCE_KEYS: [string, string][] = [
  ['j / k', 'previous / next field'],
  ['J / K', 'previous / next occurrence'],
  ['a', 'accept'],
  ['x', 'reject occurrence (delete)'],
  ['Esc', 'close'],
]
const FIELD_KEYS: [string, string][] = [
  ['j / k', 'previous / next field'],
  ['J / K', 'previous / next occurrence'],
  ['a', 'accept occurrence'],
  ['e', 'edit field'],
  ['Esc', 'close'],
]

/** A row's own control, the thing a curator changes: not its evidence icons. */
const CONTROL =
  'input, textarea, [role="combobox"], [role="switch"], button:not([data-view-evidence]):not([data-evidence-popover])'

/** One step: an occurrence, or the two of a compound-het pair. */
interface Step {
  key: string
  lines: OccurrenceRow[]
}

const stepIds = (step: Step) => step.lines.map((line) => line.occurrence.id)
const isAccepted = (step: Step) => step.lines.every((line) => line.occurrence.reviewed_at)

/** Every citation on an occurrence's evidence blocks, deduplicated: where
 * the step sits in paper order. */
function occurrenceCitations(occurrences: PatientVariantOccurrenceResp[]): Citation[] {
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
  for (const occurrence of occurrences) {
    for (const value of Object.values(occurrence)) {
      if (Array.isArray(value)) value.forEach(take)
      else take(value)
    }
  }
  return found
}

/** The individual as the occurrences table names it (PatientIdCell): the
 * pedigree symbol, the identifier, and the family beside it only when the
 * paper has more than one. */
function IndividualName({ patient, showFamily }: { patient: OccurrenceRow['patient']; showFamily: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 align-middle">
      <PedigreeSymbol patient={patient} />
      {patient.identifier}
      {showFamily && <span className="text-xs font-normal text-muted-foreground">{patient.family_identifier}</span>}
    </span>
  )
}

/** One of the occurrence's fields, laid out like the Individual and Variant
 * panels' rows (EditableField's FieldRow): label, the table's own control
 * with its evidence popover, View in PDF. The basis stays in the popover, as
 * on every other row, rather than printed under the field. */
function Field({ label, evidence, children }: { label: string; evidence?: EvidenceLike | null; children: ReactNode }) {
  return (
    <div
      data-review-field
      className="flex items-center justify-between gap-3 py-1.5 border-b last:border-0 data-[review-active=true]:rounded data-[review-active=true]:-mx-2 data-[review-active=true]:px-2 data-[review-active=true]:bg-amber-50 data-[review-active=true]:ring-2 data-[review-active=true]:ring-amber-400 dark:data-[review-active=true]:bg-amber-950/30"
    >
      <span className="text-sm text-muted-foreground shrink-0 w-44">{label}</span>
      <div className="flex items-center gap-1 flex-1 justify-end min-w-0">
        {children}
        <ViewEvidenceButton block={evidence} />
      </div>
    </div>
  )
}

function OccurrenceFields({ paperId, occurrence }: { paperId: number; occurrence: PatientVariantOccurrenceResp }) {
  return (
    <div className="text-sm">
      <Field label="Zygosity" evidence={occurrence.zygosity_evidence}>
        <EditableZygosityCell paperId={paperId} occurrence={occurrence} />
      </Field>
      <Field label="Inheritance mechanism" evidence={occurrence.inheritance_evidence}>
        <EditableInheritanceCell paperId={paperId} occurrence={occurrence} />
      </Field>
      {/* The table's De Novo switch, and only that: parent of origin is
          not shown as a value anywhere a curator works (CLAUDE.md, the
          occurrence model). */}
      <Field label="De novo" evidence={occurrence.variant_inheritance_evidence}>
        <EditableDeNovoCell paperId={paperId} occurrence={occurrence} />
      </Field>
      <Field label="Testing methods" evidence={occurrence.testing_methods_evidence[0]}>
        <EditableTestingMethodsCell paperId={paperId} occurrence={occurrence} triggerClassName="justify-end" />
      </Field>
      <Field label="Disease" evidence={occurrence.disease_name_evidence}>
        <EditableDiseaseNameCell paperId={paperId} occurrence={occurrence} />
      </Field>
      <Field label="MONDO" evidence={occurrence.mondo}>
        <MondoDiseaseCell occurrence={occurrence} />
      </Field>
    </div>
  )
}

/** A titled box in the pane; the table's own detail panels sit inside
 * the Individual and Variant ones, so the review shows and edits exactly
 * what the occurrences table's panels do. */
function Panel({ step, title, children }: { step: number; title: ReactNode; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="border-b px-3 py-2">
        <StepLabel step={step}>{title}</StepLabel>
      </div>
      {children}
    </section>
  )
}

function StepDetail({
  paperId,
  step,
  flags,
  showFamily,
}: {
  paperId: number
  step: Step
  flags: FlagIndex
  showFamily: boolean
}) {
  const patient = step.lines[0].patient
  const pair = step.lines.length > 1
  const pairReasoning = pair ? step.lines[0].occurrence.paired_variant_reasoning : null

  // The open flags about the individual, the occurrences or their variants.
  const stepFlags = useMemo(() => {
    const found = new Map<number, FlagResp>()
    const add = (list?: FlagResp[]) =>
      (list ?? []).filter((f) => f.resolved_at == null).forEach((f) => found.set(f.id, f))
    add(flags.byPatient.get(patient.id))
    const ids = new Set(stepIds(step))
    for (const line of step.lines) {
      add(flags.byOccurrence.get(line.occurrence.id))
      // A variant is shared by every carrier, so a flag reaching it through
      // another individual or another occurrence is about them, not this.
      add(
        flags.byVariant
          .get(line.variant.id)
          ?.filter(
            (f) =>
              (f.patient_id == null || f.patient_id === patient.id) &&
              (f.occurrence_id == null || ids.has(f.occurrence_id)),
          ),
      )
    }
    return [...found.values()]
  }, [flags, patient.id, step])

  const accepted = step.lines.find((line) => line.occurrence.reviewed_at)?.occurrence

  return (
    <div className="space-y-3 text-sm">
      <Panel step={1} title={pair ? 'Occurrence (compound-het pair)' : 'Occurrence'}>
        <div className="space-y-3 p-3">
          <h3 className="text-base font-semibold [overflow-wrap:anywhere]">
            <IndividualName patient={patient} showFamily={showFamily} />
            <span className="font-normal text-muted-foreground"> carries </span>
            {step.lines.map((line, index) => (
              <span key={line.occurrence.id}>
                {index > 0 && <span className="font-normal text-muted-foreground"> and </span>}
                <VariantLabel description={line.variant.variant_description} hgvsP={line.variant.hgvs_p} />
              </span>
            ))}
          </h3>
          {step.lines.map((line) => (
            <div key={line.occurrence.id}>
              {pair && (
                <p className="text-xs font-medium text-muted-foreground [overflow-wrap:anywhere]">
                  {line.variant.variant_description}
                </p>
              )}
              <OccurrenceFields paperId={paperId} occurrence={line.occurrence} />
            </div>
          ))}
          {pairReasoning && (
            <div className="text-sm">
              <Field label="Compound-het pair" evidence={pairReasoning}>
                <span>Yes</span>
                <EvidencePopover block={pairReasoning} />
              </Field>
            </div>
          )}
          {accepted && (
            <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
              <Check className="size-3.5" />
              Accepted
              {accepted.reviewed_by ? ` by ${accepted.reviewed_by.first_name}` : ''}
            </p>
          )}
          {stepFlags.length > 0 && (
            <div className="space-y-2 border-t pt-3">
              {stepFlags.map((flag) => (
                <FlagCard key={flag.id} flag={flag} />
              ))}
            </div>
          )}
        </div>
      </Panel>

      <Panel step={2} title="Individual">
        <PatientDetailPanel paperId={paperId} patient={patient} showPhenotypes={false} />
      </Panel>

      {step.lines.map((line, index) => (
        <Panel key={line.variant.id} step={3 + index} title={pair ? `Variant ${index + 1} of the pair` : 'Variant'}>
          <VariantDetailPanel paperId={paperId} variant={line.variant} />
        </Panel>
      ))}
    </div>
  )
}

export function OccurrenceReviewDialog({
  paperId,
  rows,
  flags,
  open,
  onOpenChange,
  at,
  onStep,
}: {
  paperId: number
  rows: OccurrenceRow[]
  flags: FlagIndex
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The occurrence to open on (a link's); else the first not yet accepted. */
  at?: number
  /** Told the occurrence each step shows, for the page's URL. */
  onStep?: (occurrenceId: number) => void
}) {
  const queryClient = useQueryClient()
  const { pdfUrl, filename, anchorPosition } = usePdfHighlight()
  const [currentKey, setCurrentKey] = useState<string | null>(null)
  // The field in focus within the step, as an index into the pane's
  // [data-review-field] rows in document order (the occurrence's own Field
  // rows, then the Individual and Variant panels' FieldRows); null for the
  // occurrence as a whole, 'last' until the pane has rendered a step entered
  // backwards. The pane is read rather than a list kept here, because the
  // panels decide their rows (the Variant panel's tabs change them).
  const [field, setField] = useState<number | 'last' | null>(null)
  const paneRef = useRef<HTMLDivElement>(null)
  const goTo = (key: string, at: number | 'last' | null = null) => {
    setCurrentKey(key)
    setField(at)
  }
  const fieldRows = () => [...(paneRef.current?.querySelectorAll<HTMLElement>('[data-review-field]') ?? [])]
  // What the PDF highlights: the field in focus, or a flag's evidence;
  // nothing for the occurrence as a whole. Cleared when the step changes.
  const [override, setOverride] = useState<HighlightTarget | null>(null)
  const listRef = useRef<HTMLOListElement>(null)
  const queryKey = ['occurrences', paperId]

  // The steps: pairs merged, as the table draws them; then paper order.
  const groups = useMemo(() => {
    const byId = new Map(rows.map((r) => [r.occurrence.id, r]))
    const placed = new Set<number>()
    const steps: Step[] = []
    for (const row of rows) {
      if (placed.has(row.occurrence.id)) continue
      placed.add(row.occurrence.id)
      const partnerId = row.occurrence.paired_variant_link_id
      const partner = partnerId != null && !placed.has(partnerId) ? byId.get(partnerId) : undefined
      if (partner) placed.add(partner.occurrence.id)
      const lines = partner ? [row, partner] : [row]
      steps.push({ key: lines.map((l) => l.occurrence.id).join('-'), lines })
    }
    // Each step at its first cited passage (the block, then a table's row);
    // a step citing only the supplement or nothing goes after the rest.
    const position = (step: Step): [number, number] => {
      let best: [number, number] = [Infinity, Infinity]
      for (const { anchor } of occurrenceCitations(step.lines.map((l) => l.occurrence))) {
        const at = anchorPosition(anchor)
        const here: [number, number] = at === undefined ? [1e9, 0] : [at, parseAnchor(anchor)?.row ?? -1]
        if (here[0] < best[0] || (here[0] === best[0] && here[1] < best[1])) best = here
      }
      return best
    }
    const before = (a: [number, number], b: [number, number]) => a[0] - b[0] || a[1] - b[1]
    const byFamily = new Map<
      string,
      {
        label: string
        at: [number, number]
        steps: { step: Step; at: [number, number] }[]
      }
    >()
    for (const step of steps) {
      const patient = step.lines[0].patient
      const familyKey = patient.family_id != null ? String(patient.family_id) : `none-${patient.id}`
      const at = position(step)
      const group = byFamily.get(familyKey) ?? {
        label: patient.family_identifier ?? 'No family',
        at,
        steps: [],
      }
      group.steps.push({ step, at })
      if (before(at, group.at) < 0) group.at = at
      byFamily.set(familyKey, group)
    }
    return [...byFamily.values()]
      .sort((a, b) => before(a.at, b.at) || a.label.localeCompare(b.label, undefined, { numeric: true }))
      .map((group) => ({
        label: group.label,
        steps: group.steps
          .sort(
            (a, b) =>
              before(a.at, b.at) ||
              a.step.lines[0].patient.identifier.localeCompare(b.step.lines[0].patient.identifier, undefined, {
                numeric: true,
              }),
          )
          .map(({ step }) => step),
      }))
  }, [rows, anchorPosition])

  const ordered = useMemo(() => groups.flatMap((g) => g.steps), [groups])
  const severalFamilies = useMemo(() => hasSeveralFamilies(rows.map((r) => r.patient)), [rows])
  const index = Math.max(
    0,
    ordered.findIndex((s) => s.key === currentKey),
  )
  const current: Step | undefined = ordered[index]
  const accepted = ordered.filter(isAccepted).length


  useEffect(() => setOverride(null), [current?.key])

  // The snapshot that undoes a rejection, once per opening.
  const startReview = useMutation({
    mutationFn: () =>
      startOccurrenceReviewPapersPaperIdOccurrencesReviewPost({
        path: { paper_id: paperId },
        throwOnError: true,
      }),
    onError: (error) =>
      toast.error(apiErrorMessage(error, 'Could not snapshot the paper; rejections cannot be undone')),
  })
  useEffect(() => {
    if (open) {
      startReview.mutate()
      const asked = at === undefined ? undefined : ordered.find((s) => s.lines.some((l) => l.occurrence.id === at))
      setCurrentKey((asked ?? ordered.find((s) => !isAccepted(s)) ?? ordered[0])?.key ?? null)
      setField(null)
    } else {
      setCurrentKey(null)
    }
    // Only on opening: the list changes under the review as steps are judged.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Each step into the URL, once the opening has picked one (until then the
  // first step stands in and would overwrite a link's occurrence).
  const shown = open && currentKey !== null ? current?.lines[0].occurrence.id : undefined
  useEffect(() => {
    if (shown !== undefined && shown !== at) onStep?.(shown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown])

  // Accepts and rejections show at once, not when the refetch lands, so a
  // quick second key acts on the list as the curator sees it.
  const patchCache = (update: (rows: PatientVariantOccurrenceResp[]) => PatientVariantOccurrenceResp[]) =>
    queryClient.setQueryData<PatientVariantOccurrenceResp[]>(queryKey, (data) => (data ? update(data) : data))
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey })
    queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
    // The list's progress column and, if the paper just completed, its
    // review status.
    queryClient.invalidateQueries({ queryKey: ['papers'] })
  }

  const signoff = useMutation({
    mutationFn: ({ ids, confirmed }: { ids: number[]; confirmed: boolean }) =>
      signoffRowsPapersPaperIdSignoffPost({
        path: { paper_id: paperId },
        body: { occurrence_ids: ids, confirmed },
        throwOnError: true,
      }),
    onMutate: ({ ids, confirmed }) =>
      patchCache((data) =>
        data.map((o) => (ids.includes(o.id) ? { ...o, reviewed_at: confirmed ? new Date().toISOString() : null } : o)),
      ),
    onSuccess: refresh,
    onError: (error) => {
      toast.error(apiErrorMessage(error, 'Failed to save the review'))
      refresh()
    },
  })

  const reject = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) {
        await deleteOccurrencePapersPaperIdOccurrencesOccurrenceIdDelete({
          path: { paper_id: paperId, occurrence_id: id },
          throwOnError: true,
        })
      }
    },
    onMutate: (ids) => patchCache((data) => data.filter((o) => !ids.includes(o.id))),
    onSuccess: (_data, ids) => {
      toast.success(ids.length > 1 ? 'Rejected the pair' : 'Rejected the occurrence', {
        description: "Deleted. Restore the 'Before occurrence review' snapshot to undo.",
      })
      refresh()
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, 'Failed to delete the occurrence'))
      refresh()
    },
  })

  const move = (step: number) => {
    const next = ordered[Math.max(0, Math.min(ordered.length - 1, index + step))]
    if (next) goTo(next.key)
  }

  const nextField = () => {
    const count = fieldRows().length
    const at = field === 'last' ? count - 1 : field
    if (at === null ? count > 0 : at < count - 1) setField(at === null ? 0 : at + 1)
    else if (ordered[index + 1]) goTo(ordered[index + 1].key)
  }

  const previousField = () => {
    const at = field === 'last' ? fieldRows().length - 1 : field
    if (at !== null && at > 0) setField(at - 1)
    else if (at === 0) setField(null)
    else if (ordered[index - 1]) goTo(ordered[index - 1].key, 'last')
  }

  // Outline the field in focus, bring it into view and narrow the PDF to it
  // (through its own View in PDF button, so the highlight is exactly what
  // the row's icon shows); a field citing nothing highlights nothing. On the
  // occurrence as a whole, the pane goes back to its top.
  useEffect(() => {
    const rows = fieldRows()
    rows.forEach((row) => row.removeAttribute('data-review-active'))
    if (field === 'last') {
      setField(rows.length > 0 ? rows.length - 1 : null)
      return
    }
    if (field === null) {
      paneRef.current?.scrollTo({ top: 0 })
      setOverride(null)
      return
    }
    const row = rows[field]
    if (!row) return
    row.setAttribute('data-review-active', 'true')
    // Glide the row to the top of the pane (a few pixels clear of it), on
    // the pane alone: scrollIntoView also moved the dialog around it, and
    // centring an instant jump made a click on a field lurch.
    const pane = paneRef.current
    if (pane) {
      const offset = row.getBoundingClientRect().top - pane.getBoundingClientRect().top
      pane.scrollTo({ top: pane.scrollTop + offset - 8, behavior: 'smooth' })
    }
    const view = row.querySelector<HTMLButtonElement>('[data-view-evidence]:not(:disabled)')
    if (view) view.click()
    else setOverride(null)
  }, [current?.key, field])

  const accept = () => {
    if (!current) return
    const acceptNow = !isAccepted(current)
    signoff.mutate({ ids: stepIds(current), confirmed: acceptNow })
    if (!acceptNow) return
    // On to the next step not yet accepted, after this one, wrapping round.
    const after = [...ordered.slice(index + 1), ...ordered.slice(0, index)]
    const next = after.find((s) => !isAccepted(s))
    if (next) goTo(next.key)
  }

  const rejectCurrent = () => {
    if (!current) return
    // Stay at this place in the list: the step after, or before at the end.
    const next = ordered[index + 1] ?? ordered[index - 1]
    reject.mutate(stepIds(current))
    setCurrentKey(next?.key ?? null)
    setField(null)
  }

  useReviewKeys(open, {
    j: previousField,
    k: nextField,
    J: () => move(-1),
    K: () => move(1),
    a: accept,
    x: () => field === null && rejectCurrent(),
    e: () => {
      if (typeof field !== 'number') return
      const control = fieldRows()[field]?.querySelector<HTMLElement>(CONTROL)
      if (control) control.focus()
      else toast('This field is read-only here')
    },
  })

  // Keep the current step in view in a long list.
  useEffect(() => {
    listRef.current?.querySelector('[data-current="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [current?.key])

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Esc in an edit's note dialog reaches this one too; it closes only that.
        if (!next && dialogAbove()) return
        onOpenChange(next)
      }}
    >
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col gap-0 p-0 sm:max-w-[96vw]">
        <div className="flex items-center justify-between gap-4 border-b px-4 py-3 pr-12">
          <DialogTitle>Occurrence review</DialogTitle>
          <span className="text-sm text-muted-foreground">
            {accepted} of {ordered.length} accepted
          </span>
        </div>
        <PdfHighlightProvider paperId={paperId} pdfUrl={pdfUrl} filename={filename} inline={setOverride}>
          <ReviewSplit
            review={
              <>
                <ol ref={listRef} className="max-h-[35%] overflow-y-auto border-b p-2 text-sm">
                  {groups.map((group) => (
                    <li key={group.label}>
                      <p className="px-2 pt-1.5 pb-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {group.label}
                      </p>
                      <ol>
                        {group.steps.map((step) => (
                          <li key={step.key}>
                            <button
                              type="button"
                              data-current={step.key === current?.key}
                              onClick={() => goTo(step.key)}
                              className={cn(
                                'flex w-full items-center gap-2 rounded px-2 py-1 text-left cursor-pointer hover:bg-muted',
                                step.key === current?.key && 'bg-muted font-medium',
                              )}
                            >
                              {isAccepted(step) ? (
                                <Check className="size-3.5 shrink-0 text-emerald-600" />
                              ) : (
                                <Circle className="size-3.5 shrink-0 text-muted-foreground" />
                              )}
                              <span className="shrink-0">{step.lines[0].patient.identifier}</span>
                              <span className="ml-auto truncate text-xs text-muted-foreground">
                                {step.lines.map((l) => l.variant.variant_description).join(' + ')}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ol>
                    </li>
                  ))}
                </ol>
                {/* A click in a field makes it the field in focus, so j/k go on
                  from where the curator is working. */}
                <div
                  ref={paneRef}
                  className="min-h-0 flex-1 overflow-y-auto p-4"
                  onClickCapture={(event) => {
                    const row = (event.target as HTMLElement).closest('[data-review-field]')
                    const at = row ? fieldRows().indexOf(row as HTMLElement) : -1
                    if (at >= 0 && at !== field) setField(at)
                  }}
                >
                  {current ? (
                    <StepDetail paperId={paperId} step={current} flags={flags} showFamily={severalFamilies} />
                  ) : (
                    <p className="text-sm text-muted-foreground">No occurrences left to review.</p>
                  )}
                </div>
                <KeyLegend keys={field === null ? OCCURRENCE_KEYS : FIELD_KEYS} />
              </>
            }
            pdf={
              <EvidencePanes
                paperId={paperId}
                pdfUrl={pdfUrl}
                filename={filename}
                target={override}
              />
            }
          />
        </PdfHighlightProvider>
      </DialogContent>
    </Dialog>
  )
}
