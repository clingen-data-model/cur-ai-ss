/* Re-runs the agent that raised a flag, for the row it ran on -- the flag's
 * counterpart to ScopedRerunButton, which the server scopes itself from the
 * flag (see POST /papers/{id}/flags/{flag_id}/rerun). The flag is replaced
 * by whatever the agent raises on that run, so this is the "ask again" half
 * of review next to Resolve ("keep it") and the row's trashcan ("drop it").
 *
 * The paper's one Additional context field is on show (PaperContextField),
 * because the note does not go to this run alone: the server appends "A
 * curator reviewed the <agent> flag ... Their note: ..." to that field, where
 * it stays for every later run of every agent. Seeing the field, with the
 * paragraphs earlier reviews left in it, is what makes that plain -- and the
 * place to prune them. */
import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { FlagResp } from '@/api/generated/types.gen'
import { PaperContextField } from '@/components/PaperContextField'
import { usePaperBusy } from '@/hooks/usePaperBusy'
import { usePaperAdditionalContext } from '@/hooks/usePaperAdditionalContext'
import { flagSourceLabel } from '@/lib/flags'

export function RerunFromFlagDialog({
  paperId,
  flag,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: {
  paperId: number
  flag: FlagResp | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (input: { context: string; note: string }) => void
  isPending?: boolean
}) {
  const [note, setNote] = useState('')
  const [context, setContext] = useState('')
  const busy = usePaperBusy(paperId, open)
  const paperContext = usePaperAdditionalContext(paperId, open)

  useEffect(() => {
    if (open) setNote('')
  }, [open, flag?.id])
  useEffect(() => {
    if (open && paperContext.loaded) setContext(paperContext.context ?? '')
    // Only when the dialog opens or the context first loads: a refetch while
    // it is open must not overwrite what the curator has typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, paperContext.loaded])

  const agent = flag ? flagSourceLabel(flag) : 'agent'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Re-run {agent}</DialogTitle>
          <DialogDescription>
            Runs the agent again for the row it flagged, telling it a curator looked at{' '}
            <span className="font-medium text-foreground">{flag?.subject}</span>. The flag is
            replaced by whatever that run raises; the row is snapshotted first.
          </DialogDescription>
        </DialogHeader>
        <PaperContextField value={context} onChange={setContext} disabled={!paperContext.loaded} />
        <div className="space-y-1.5">
          <Label>
            Note to the agent <span className="text-muted-foreground font-normal">(optional)</span>
          </Label>
          <Textarea
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What it missed, or where to look..."
            rows={3}
          />
          <p className="text-xs text-muted-foreground">
            Added to the end of the context above as &ldquo;A curator reviewed the {agent} flag
            &lsquo;{flag?.subject}&rsquo; and asked for that step to run again. Their note:
            &hellip;&rdquo; It stays there for every later run; remove it from the box above when
            it no longer applies.
          </p>
        </div>
        {busy && <p className="text-sm text-amber-700 dark:text-amber-400">{busy}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => onConfirm({ context, note: note.trim() })}
            disabled={isPending || !!busy || !paperContext.loaded}
          >
            <RefreshCw className="size-3.5 mr-1.5" />
            {isPending ? 'Queuing...' : 'Re-run'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
