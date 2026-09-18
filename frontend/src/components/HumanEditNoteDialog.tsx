/* Forces a curator note before a manual edit commits.
 *
 * The Streamlit UI silently fills a placeholder note when a field changes;
 * here the curator must type their own reasoning before the edit saves.
 */
import { useEffect, useState } from 'react'
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
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  fieldLabel: string
  defaultNote?: string | null
  onConfirm: (note: string) => void
  isPending?: boolean
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
