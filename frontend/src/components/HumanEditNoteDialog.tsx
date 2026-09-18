/* Forces a curator note before a manual edit commits.
 *
 * The Streamlit UI silently fills a placeholder note when a field changes;
 * here the curator must type their own reasoning before the edit saves.
 */
import { useEffect, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Textarea } from '@/components/ui/textarea'

export function HumanEditNoteDialog({
  open,
  onOpenChange,
  fieldLabel,
  defaultNote,
  onConfirm,
  isPending,
  beforeValue,
  afterValue,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  fieldLabel: string
  defaultNote?: string | null
  onConfirm: (note: string) => void
  isPending?: boolean
  /** The field's current and proposed values, formatted for display. Shown as
   * a "before -> after" line when both are given; omitted otherwise so a
   * caller that hasn't been updated yet still renders correctly. */
  beforeValue?: string
  afterValue?: string
}) {
  const [note, setNote] = useState('')

  // Re-seed from the field's existing note each time the dialog opens for a
  // (possibly different) field, rather than carrying over the last field's text.
  useEffect(() => {
    if (open) setNote(defaultNote ?? '')
  }, [open, defaultNote])

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Explain this change</AlertDialogTitle>
          <AlertDialogDescription>
            Add a note explaining why <span className="font-medium text-foreground">{fieldLabel}</span> is
            being manually overridden. This is required before the change saves.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {beforeValue !== undefined && afterValue !== undefined && (
          <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
            <span className="text-muted-foreground line-through truncate">{beforeValue || '—'}</span>
            <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="font-medium truncate">{afterValue || '—'}</span>
          </div>
        )}
        <Textarea
          autoFocus
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Reasoning behind the change..."
          maxLength={120}
          rows={3}
        />
        <AlertDialogFooter>
          <AlertDialogCancel variant="outline">Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={!note.trim() || isPending}
            onClick={() => onConfirm(note.trim())}
          >
            {isPending ? 'Saving...' : 'Save'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
