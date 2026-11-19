/* The HPO review: one individual's phenotypes, one term at a time, beside the
 * PDF with that term's passage highlighted. Curators had been checking terms
 * from the phenotype table, where each one took the evidence popover, then
 * the HPO popover, then View in PDF; here the paper's words, both reasonings
 * and the highlighted passage are all on screen for the current term, and
 * the keyboard moves through them:
 *
 *   j / k  previous / next term
 *   a      accept: stamp the term as reviewed (lib/models/signoff.py) and go
 *          to the next unreviewed one; on an accepted term, take it back
 *   r      relink: RelinkHpoDialog for the current term (relinking clears
 *          the stamp, since the term judged has changed)
 *   x      reject: delete the phenotype, as the table's delete does
 *
 * Opening the review writes a snapshot ("Before HPO review: <individual>"),
 * which is how a rejection is undone: deletes are not reversible otherwise.
 *
 * Terms are listed in paper order, by the first passage each cites.
 *
 * The modal renders the PDF itself (EvidencePanes) and wraps its body in an
 * inline PdfHighlightProvider, so a flag's View in PDF lands in this pane
 * rather than opening the paper page's sheet on top of the modal -- the same
 * arrangement as the Review Mode page. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check, Circle, FileSearch } from 'lucide-react'
import {
  deletePhenotypePapersPaperIdPhenotypesPhenotypeIdDelete,
  signoffPhenotypesPapersPaperIdPhenotypesSignoffPost,
  startHpoReviewPapersPaperIdIndividualsPatientIdPhenotypesReviewPost,
} from '@/api/generated'
import type { Citation, PhenotypeResp } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import {
  EvidencePanes,
  PdfHighlightProvider,
  usePdfHighlight,
  type HighlightTarget,
} from '@/components/PdfHighlightProvider'
import { RelinkHpoDialog } from '@/components/RelinkHpoDialog'
import { FlagCard } from '@/components/FlagIndicator'
import { usePaperFlags } from '@/hooks/usePaperFlags'
import { describeAnchor, parseAnchor } from '@/lib/anchors'
import { apiErrorMessage } from '@/lib/apiError'
import { cn } from '@/lib/utils'

const KEYS: [string, string][] = [
  ['j / k', 'previous / next'],
  ['a', 'accept'],
  ['r', 'relink'],
  ['x', 'reject (delete)'],
  ['Esc', 'close'],
]

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

function Quotes({ citations }: { citations: Citation[] }) {
  const { anchorPage, openHighlight } = usePdfHighlight()
  if (citations.length === 0) return <p className="text-muted-foreground">No passage cited.</p>
  return (
    <ul className="space-y-1">
      {citations.map((citation, index) => (
        <li key={`${citation.anchor}-${index}`}>
          <button
            type="button"
            className="flex w-full items-start gap-1.5 rounded text-left hover:bg-muted cursor-pointer"
            onClick={() => openHighlight({ citations: [citation] })}
          >
            <Badge variant="outline" className="shrink-0 font-normal">
              {describeAnchor(citation.anchor, anchorPage(citation.anchor))}
            </Badge>
            {citation.quote && (
              <span className="min-w-0 [overflow-wrap:anywhere]">“{citation.quote}”</span>
            )}
          </button>
        </li>
      ))}
    </ul>
  )
}

function TermDetail({
  paperId,
  phenotype,
  relinkOpen,
  onRelinkOpenChange,
}: {
  paperId: number
  phenotype: PhenotypeResp
  relinkOpen: boolean
  onRelinkOpenChange: (open: boolean) => void
}) {
  const flags = usePaperFlags(paperId)
  const { openHighlight } = usePdfHighlight()
  const hpo = phenotype.hpo.value
  const termFlags = flags.byPhenotype.get(phenotype.id) ?? []
  const details = [
    phenotype.onset && `Onset: ${phenotype.onset}`,
    phenotype.location && `Location: ${phenotype.location}`,
    phenotype.severity && `Severity: ${phenotype.severity}`,
    phenotype.modifier && `Modifier: ${phenotype.modifier}`,
  ].filter(Boolean)
  const citations = phenotype.concept_evidence.citations ?? []

  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <h3 className="text-base font-semibold">{phenotype.concept}</h3>
          {phenotype.negated && <Badge variant="outline">Negated</Badge>}
          {phenotype.uncertain && <Badge variant="outline">Uncertain</Badge>}
          {phenotype.family_history && <Badge variant="outline">Family history</Badge>}
          {phenotype.reviewed_at && (
            <Badge className="bg-emerald-600 text-white">
              Accepted{phenotype.reviewed_by ? ` by ${phenotype.reviewed_by.first_name}` : ''}
            </Badge>
          )}
        </div>
        {details.length > 0 && (
          <p className="text-xs text-muted-foreground">{details.join(' · ')}</p>
        )}
        <Quotes citations={citations} />
        {phenotype.concept_evidence.reasoning && (
          <p className="break-words">
            <span className="font-medium">Reasoning: </span>
            {phenotype.concept_evidence.reasoning}
          </p>
        )}
        {citations.length > 1 && (
          <Button variant="ghost" size="sm" className="gap-1.5 px-2" onClick={() => openHighlight({ citations })}>
            <FileSearch className="size-3.5" />
            Highlight every passage
          </Button>
        )}
      </section>

      <section className="space-y-2 border-t pt-3">
        <div className="flex items-center gap-2">
          <span className="font-medium">HPO</span>
          {hpo ? (
            <>
              <span>{hpo.name}</span>
              <a
                href={`https://hpo.jax.org/app/browse/term/${hpo.id}`}
                target="_blank"
                rel="noreferrer"
                className="text-link hover:underline"
              >
                <code className="text-xs">{hpo.id}</code>
              </a>
            </>
          ) : (
            <span className="text-muted-foreground">No match</span>
          )}
          <RelinkHpoDialog
            paperId={paperId}
            phenotypeId={phenotype.id}
            concept={phenotype.concept}
            currentHpoId={hpo?.id ?? null}
            currentHpoName={hpo?.name ?? null}
            open={relinkOpen}
            onOpenChange={onRelinkOpenChange}
          />
        </div>
        {phenotype.hpo.reasoning && (
          <p className="break-words">
            <span className="font-medium">Link reasoning: </span>
            {phenotype.hpo.reasoning}
          </p>
        )}
        {phenotype.hpo.edited_by_name && (
          <p className="text-xs text-muted-foreground">Linked by {phenotype.hpo.edited_by_name}</p>
        )}
      </section>

      {termFlags.length > 0 && (
        <section className="space-y-2 border-t pt-3">
          {termFlags.map((flag) => (
            <FlagCard key={flag.id} flag={flag} />
          ))}
        </section>
      )}
    </div>
  )
}

export function HpoReviewDialog({
  paperId,
  patientId,
  phenotypes,
  open,
  onOpenChange,
}: {
  paperId: number
  patientId: number
  phenotypes: PhenotypeResp[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { pdfUrl, filename, anchorPosition } = usePdfHighlight()
  const [currentId, setCurrentId] = useState<number | null>(null)
  const [relinkOpen, setRelinkOpen] = useState(false)
  // A narrower highlight (one quote, a flag's evidence) until the term changes.
  const [override, setOverride] = useState<HighlightTarget | null>(null)
  const listRef = useRef<HTMLOListElement>(null)
  const queryKey = ['phenotypes', paperId, patientId]

  // Paper order: each term at its first cited passage (the table's place for
  // a row, then the row), so a curator reads the paper top to bottom. Terms
  // citing only the supplement follow, then terms citing nothing (added by
  // hand), alphabetically within each.
  const ordered = useMemo(() => {
    const key = (p: PhenotypeResp): [number, number] => {
      let best: [number, number] = [Infinity, Infinity]
      for (const { anchor } of p.concept_evidence.citations ?? []) {
        const at = anchorPosition(anchor)
        const row = parseAnchor(anchor)?.row ?? -1
        const here: [number, number] = at === undefined ? [1e9, 0] : [at, row]
        if (here[0] < best[0] || (here[0] === best[0] && here[1] < best[1])) best = here
      }
      return best
    }
    return phenotypes
      .map((p) => ({ p, k: key(p) }))
      .sort((a, b) => a.k[0] - b.k[0] || a.k[1] - b.k[1] || a.p.concept.localeCompare(b.p.concept))
      .map(({ p }) => p)
  }, [phenotypes, anchorPosition])

  const index = Math.max(0, ordered.findIndex((p) => p.id === currentId))
  const current: PhenotypeResp | undefined = ordered[index]
  const reviewed = ordered.filter((p) => p.reviewed_at).length

  const termTarget = useMemo<HighlightTarget | null>(
    () =>
      current && (current.concept_evidence.citations ?? []).length > 0
        ? { citations: current.concept_evidence.citations ?? [] }
        : null,
    [current],
  )
  const target = override ?? termTarget

  useEffect(() => setOverride(null), [current?.id])

  // The snapshot that undoes a rejection, once per opening.
  const startReview = useMutation({
    mutationFn: () =>
      startHpoReviewPapersPaperIdIndividualsPatientIdPhenotypesReviewPost({
        path: { paper_id: paperId, patient_id: patientId },
        throwOnError: true,
      }),
    onError: (error) =>
      toast.error(apiErrorMessage(error, 'Could not snapshot the paper; rejections cannot be undone')),
  })
  useEffect(() => {
    if (open) {
      startReview.mutate()
      setCurrentId((ordered.find((p) => !p.reviewed_at) ?? ordered[0])?.id ?? null)
    }
    // Only on opening: the list changes under the review as terms are judged.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Accepts and rejections show at once, not when the refetch lands, so a
  // quick second key acts on the list as the curator sees it: the next
  // unreviewed term skips one just accepted, and x never meets a row it has
  // already deleted.
  const patchCache = (update: (rows: PhenotypeResp[]) => PhenotypeResp[]) =>
    queryClient.setQueryData<PhenotypeResp[]>(queryKey, (rows) => (rows ? update(rows) : rows))
  const refresh = () => queryClient.invalidateQueries({ queryKey })

  const signoff = useMutation({
    mutationFn: ({ id, reviewed }: { id: number; reviewed: boolean }) =>
      signoffPhenotypesPapersPaperIdPhenotypesSignoffPost({
        path: { paper_id: paperId },
        body: { phenotype_ids: [id], reviewed },
        throwOnError: true,
      }),
    onMutate: ({ id, reviewed }) =>
      patchCache((rows) =>
        rows.map((p) =>
          p.id === id ? { ...p, reviewed_at: reviewed ? new Date().toISOString() : null } : p,
        ),
      ),
    onSuccess: (response) => {
      const fresh = new Map(response.map((p) => [p.id, p]))
      patchCache((rows) => rows.map((p) => fresh.get(p.id) ?? p))
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, 'Failed to save the review'))
      refresh()
    },
  })

  const reject = useMutation({
    mutationFn: (id: number) =>
      deletePhenotypePapersPaperIdPhenotypesPhenotypeIdDelete({
        path: { paper_id: paperId, phenotype_id: id },
        throwOnError: true,
      }),
    onMutate: (id) => patchCache((rows) => rows.filter((p) => p.id !== id)),
    onSuccess: (_data, id) => {
      const concept = phenotypes.find((p) => p.id === id)?.concept
      toast.success(`Rejected ${concept ?? 'phenotype'}`, {
        description: "Deleted. Restore the 'Before HPO review' snapshot to undo.",
      })
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, 'Failed to delete phenotype'))
      refresh()
    },
  })

  const move = (step: number) => {
    const next = ordered[Math.max(0, Math.min(ordered.length - 1, index + step))]
    if (next) setCurrentId(next.id)
  }

  const accept = () => {
    if (!current) return
    const reviewedNow = !current.reviewed_at
    signoff.mutate({ id: current.id, reviewed: reviewedNow })
    if (!reviewedNow) return
    // On to the next term not yet reviewed, after this one, wrapping round.
    const after = [...ordered.slice(index + 1), ...ordered.slice(0, index)]
    const next = after.find((p) => !p.reviewed_at)
    if (next) setCurrentId(next.id)
  }

  const rejectCurrent = () => {
    if (!current) return
    // Stay at this place in the list: the term after, or before at the end.
    const next = ordered[index + 1] ?? ordered[index - 1]
    reject.mutate(current.id)
    setCurrentId(next?.id ?? null)
  }

  useEffect(() => {
    if (!open || relinkOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return
      const actions: Record<string, () => void> = {
        j: () => move(-1),
        k: () => move(1),
        a: accept,
        r: () => current && setRelinkOpen(true),
        x: rejectCurrent,
      }
      const action = actions[event.key]
      if (action) {
        event.preventDefault()
        action()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // Keep the current term in view in a long list.
  useEffect(() => {
    listRef.current?.querySelector('[data-current="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [current?.id])

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Esc in the relink dialog reaches this one too; it closes only that.
        if (!next && relinkOpen) return
        onOpenChange(next)
      }}
    >
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col gap-0 p-0 sm:max-w-[96vw]">
        <div className="flex items-center justify-between gap-4 border-b px-4 py-3 pr-12">
          <DialogTitle>HPO review</DialogTitle>
          <span className="text-sm text-muted-foreground">
            {reviewed} of {ordered.length} accepted
          </span>
        </div>
        <PdfHighlightProvider paperId={paperId} pdfUrl={pdfUrl} filename={filename} inline={setOverride}>
          <div className="flex min-h-0 flex-1">
            <div className="flex w-[26rem] shrink-0 flex-col border-r">
              <ol ref={listRef} className="max-h-[40%] overflow-y-auto border-b p-2 text-sm">
                {ordered.map((phenotype) => (
                  <li key={phenotype.id}>
                    <button
                      type="button"
                      data-current={phenotype.id === current?.id}
                      onClick={() => setCurrentId(phenotype.id)}
                      className={cn(
                        'flex w-full items-center gap-2 rounded px-2 py-1 text-left cursor-pointer hover:bg-muted',
                        phenotype.id === current?.id && 'bg-muted font-medium',
                      )}
                    >
                      {phenotype.reviewed_at ? (
                        <Check className="size-3.5 shrink-0 text-emerald-600" />
                      ) : (
                        <Circle className="size-3.5 shrink-0 text-muted-foreground" />
                      )}
                      <span className="truncate">{phenotype.concept}</span>
                      <span className="ml-auto truncate text-xs text-muted-foreground">
                        {phenotype.hpo.value?.name ?? 'No match'}
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                {current ? (
                  <TermDetail
                    paperId={paperId}
                    phenotype={current}
                    relinkOpen={relinkOpen}
                    onRelinkOpenChange={setRelinkOpen}
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">No phenotypes left to review.</p>
                )}
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 border-t px-4 py-2 text-xs text-muted-foreground">
                {KEYS.map(([key, label]) => (
                  <span key={key}>
                    <kbd className="rounded border bg-muted px-1 font-mono">{key}</kbd> {label}
                  </span>
                ))}
              </div>
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
              <EvidencePanes paperId={paperId} pdfUrl={pdfUrl} filename={filename} target={target} />
            </div>
          </div>
        </PdfHighlightProvider>
      </DialogContent>
    </Dialog>
  )
}
