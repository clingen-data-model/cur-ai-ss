/* Re-runs the agent that raised a flag, for the row it ran on, with the
 * curator's note as its follow-up context -- the flag's counterpart to
 * ScopedRerunButton, which the server scopes itself from the flag (see
 * POST /papers/{id}/flags/{flag_id}/rerun). The flag is replaced by whatever
 * the agent raises on that run, so this is the "ask again" half of review
 * next to Resolve ("keep it") and the row's trashcan ("drop it"). */
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
import { usePaperBusy } from '@/hooks/usePaperBusy'
import { QuickRunCheckbox } from '@/components/QuickRunCheckbox'
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
  onConfirm: (note: string, budgetModel: boolean) => void
  isPending?: boolean
}) {
  const [note, setNote] = useState('')
  const [budgetModel, setBudgetModel] = useState(false)
  const busy = usePaperBusy(paperId, open)

  useEffect(() => {
    if (open) {
      setNote('')
      setBudgetModel(false)
    }
  }, [open, flag?.id])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Re-run {flag ? flagSourceLabel(flag) : 'agent'}</DialogTitle>
          <DialogDescription>
            Runs the agent again for the row it flagged, telling it a curator looked at{' '}
            <span className="font-medium text-foreground">{flag?.subject}</span>. The flag is
            replaced by whatever that run raises; the row is snapshotted first.
          </DialogDescription>
        </DialogHeader>
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
        </div>
        <QuickRunCheckbox checked={budgetModel} onChange={setBudgetModel} />
        {busy && <p className="text-sm text-amber-700 dark:text-amber-400">{busy}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => onConfirm(note.trim(), budgetModel)}
            disabled={isPending || !!busy}
          >
            <RefreshCw className="size-3.5 mr-1.5" />
            {isPending ? 'Queuing...' : 'Re-run'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
