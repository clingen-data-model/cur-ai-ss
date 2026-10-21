/* Re-runs the agent that raised a flag, for the row it ran on -- the flag's
 * counterpart to ScopedRerunButton, which the server scopes itself from the
 * flag (see POST /papers/{id}/flags/{flag_id}/rerun). The flag is replaced
 * by whatever the agent raises on that run, so this is the "ask again" half
 * of review next to Resolve ("keep it") and the row's trashcan ("drop it").
 *
 * The paper's context notes are on show (PaperContextNotes), because the
 * note does not go to this run alone: the server saves it as a note
 * labelled with the agent, the row and the flag, which every agent reads on
 * every later run. Re-running the same flag again replaces that note; the
 * list is where to remove one that no longer applies. */
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
import type { FlagResp } from '@/api/generated/types.gen'
import { PaperContextNotes } from '@/components/PaperContextNotes'
import { usePaperBusy } from '@/hooks/usePaperBusy'
import { usePaperContextNotes } from '@/hooks/usePaperContextNotes'
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
  onConfirm: (note: string) => void
  isPending?: boolean
}) {
  const [note, setNote] = useState('')
  const busy = usePaperBusy(paperId, open)
  const notes = usePaperContextNotes(paperId, open)

  useEffect(() => {
    if (open) setNote('')
  }, [open, flag?.id])

  const agent = flag ? flagSourceLabel(flag) : 'agent'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Re-run {agent}</DialogTitle>
          <DialogDescription>
            Runs the agent again for the row it flagged as{' '}
            <span className="font-medium text-foreground">{flag?.subject}</span>. The flag is
            replaced by whatever that run raises; the row is snapshotted first.
          </DialogDescription>
        </DialogHeader>
        <PaperContextNotes
          paperId={paperId}
          notes={notes}
          value={note}
          onChange={setNote}
          addLabel="Note to the agent"
          addPlaceholder="What it missed, or where to look..."
          addHelp={`Saved as a note labelled “${agent}”, this row and the flag: every agent reads it on every later run too, until it is removed above. Re-running this flag again replaces it.`}
        />
        {busy && <p className="text-sm text-amber-700 dark:text-amber-400">{busy}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => onConfirm(note.trim())} disabled={isPending || !!busy}>
            <RefreshCw className="size-3.5 mr-1.5" />
            {isPending ? 'Queuing...' : 'Re-run'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
