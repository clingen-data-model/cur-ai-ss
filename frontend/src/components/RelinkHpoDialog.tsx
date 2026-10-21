/* Per-row action to change which HPO term a phenotype is linked to -- for
 * correcting a wrong auto-match or linking one manually where extraction
 * found none. Mirrors LinkVariantDialog's icon-button-trigger shape but
 * edits an existing row instead of creating a new link. The trigger icon
 * signals which of the two flows below this opens on: a pencil for picking a
 * term for the first time ("manual edit"), a refresh icon for replacing an
 * existing one ("re-link").
 *
 * Two ways to change the link, as separate tabs rather than one combined
 * flow: "Pick a term" is the fast path -- a curator who already knows the
 * right term searches and picks it directly, writing straight to the
 * phenotype's HPO link with no agent involved. "Re-run agent" instead queues
 * the HPO_LINKING task for just this phenotype (the same task-queue endpoint
 * PaperActions.tsx's paper-wide "Rerun Agents" button uses), with the paper's
 * context notes on show, and a box to add one (PaperContextNotes) -- for when
 * the curator wants the agent to try again with a hint rather than overriding
 * it by hand. That queues async work on the worker, so there is no immediate
 * result here beyond a confirmation toast; the row picks up the new match
 * whenever the phenotypes list is next refetched.
 *
 * The trigger icon for an existing link is the same RefreshCw PaperActions.tsx
 * and TaskTimeline.tsx use for "re-run this agent" -- both open onto a re-run
 * flow (this one via a tab, since a manual pick is also on offer), so the icon
 * means the same thing everywhere it appears. */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Pencil, RefreshCw } from 'lucide-react'
import {
  createTaskPapersPaperIdTasksPost,
  relinkPhenotypeHpoPapersPaperIdPhenotypesPhenotypeIdHpoPatch,
} from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { HpoCombobox } from '@/components/HpoCombobox'
import { PaperContextNotes } from '@/components/PaperContextNotes'
import { apiErrorMessage } from '@/lib/apiError'
import { usePaperBusy } from '@/hooks/usePaperBusy'
import { usePaperContextNotes } from '@/hooks/usePaperContextNotes'

export function RelinkHpoDialog({
  paperId,
  phenotypeId,
  concept,
  currentHpoId,
  currentHpoName,
}: {
  paperId: number
  phenotypeId: number
  concept: string
  currentHpoId: string | null
  currentHpoName: string | null
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [hpoId, setHpoId] = useState<string | null>(currentHpoId)
  const [context, setContext] = useState('')
  const hasExistingLink = currentHpoId != null

  const reset = () => {
    setHpoId(currentHpoId)
    setContext('')
  }

  const relinkMutation = useMutation({
    mutationKey: ['paper-edit', paperId],
    mutationFn: (nextHpoId: string | null) =>
      relinkPhenotypeHpoPapersPaperIdPhenotypesPhenotypeIdHpoPatch({
        path: { paper_id: paperId, phenotype_id: phenotypeId },
        body: { hpo_id: nextHpoId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['phenotypes', paperId] })
      toast.success('HPO link updated')
      setOpen(false)
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to update HPO link')),
  })

  // The manual tab writes directly and stays usable; only the agent tab
  // queues a task, which the API refuses while the paper is busy.
  const busy = usePaperBusy(paperId, open)
  const notes = usePaperContextNotes(paperId, open)

  const rerunMutation = useMutation({
    mutationFn: () =>
      createTaskPapersPaperIdTasksPost({
        path: { paper_id: paperId },
        body: {
          type: 'HPO Linking',
          phenotype_id: phenotypeId,
          additional_context: context,
          skip_successors: false,
        },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-tasks', paperId] })
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
      toast.success('HPO linking agent queued')
      setOpen(false)
      setContext('')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to queue agent re-run')),
  })

  return (
    <>
      <button
        type="button"
        title={hasExistingLink ? 'Re-link HPO term' : 'Link HPO term'}
        onClick={(e) => {
          e.stopPropagation()
          reset()
          setOpen(true)
        }}
        className="inline-flex items-center justify-center size-7 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
      >
        {hasExistingLink ? <RefreshCw className="size-3.5" /> : <Pencil className="size-3.5" />}
      </button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) reset()
        }}
      >
        <DialogContent onClick={(e) => e.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>{hasExistingLink ? 'Re-link HPO Term' : 'Link HPO Term'}</DialogTitle>
            <DialogDescription>
              {hasExistingLink ? (
                <>
                  Change which HPO term{' '}
                  <span className="font-medium text-foreground">{concept}</span> is linked to.
                </>
              ) : (
                <>
                  Link <span className="font-medium text-foreground">{concept}</span> to an HPO
                  term.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <Tabs defaultValue="pick">
            <TabsList>
              <TabsTrigger value="pick">Pick a term</TabsTrigger>
              <TabsTrigger value="agent">Re-run agent</TabsTrigger>
            </TabsList>
            <TabsContent value="pick" className="space-y-4 pt-3">
              <div className="space-y-1.5">
                <Label>HPO Term</Label>
                <HpoCombobox
                  value={hpoId}
                  initialLabel={currentHpoName}
                  onValueChange={(id) => setHpoId(id)}
                  autoFocus
                />
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => relinkMutation.mutate(hpoId)}
                  disabled={relinkMutation.isPending || hpoId === currentHpoId}
                >
                  {relinkMutation.isPending ? 'Saving...' : hasExistingLink ? 'Save' : 'Link'}
                </Button>
              </DialogFooter>
            </TabsContent>
            <TabsContent value="agent" className="space-y-4 pt-3">
              <PaperContextNotes
                paperId={paperId}
                notes={notes}
                value={context}
                onChange={setContext}
                addHelp={`Saved as a note labelled “HPO Linking” and this phenotype: every agent reads it on every later run too, until it is removed above.`}
              />
              <p className="text-xs text-muted-foreground">
                Re-runs the HPO linking agent for this phenotype in the background. The result
                will show up here once it's done.
              </p>
              {busy && <p className="text-sm text-amber-700 dark:text-amber-400">{busy}</p>}
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => rerunMutation.mutate()}
                  disabled={rerunMutation.isPending || !!busy}
                >
                  {rerunMutation.isPending ? 'Queuing...' : 'Re-run agent'}
                </Button>
              </DialogFooter>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  )
}
