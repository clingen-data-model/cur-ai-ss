/* The one Additional context box, shared by every dialog that queues a run:
 * the paper-wide re-run dialog (PaperActions.tsx) and the per-row ones
 * (ScopedRerunButton, RelinkHpoDialog, PairOccurrenceDialog). There is one
 * context per paper, read by every agent on every run, so each dialog shows
 * the same field with the same words -- edit it in place, and what is sent
 * back is what every later run sees. A task has no context of its own: it
 * used to, as a follow-up to that task's last run, and a curator who picked
 * the wrong task left the right agent unaware of it. */
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export const PAPER_CONTEXT_NOTE =
  'One context for the whole paper: every agent reads it on every run, and it stays until changed. ' +
  'If an instruction is for one step, name it, e.g. “HPO Linking: treat all seizures as febrile.”'

export function PaperContextField({
  value,
  onChange,
  disabled = false,
}: {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <Label>
        Additional context <span className="text-muted-foreground font-normal">(optional)</span>
      </Label>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Anything the agents should know about this paper..."
        rows={4}
        disabled={disabled}
      />
      <p className="text-xs text-muted-foreground">{PAPER_CONTEXT_NOTE}</p>
    </div>
  )
}
