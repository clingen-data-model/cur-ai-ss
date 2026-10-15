/* Resolves every flag the Flags tab is showing, with one note. Same
 * one-way rule as ResolveFlagDialog, and the same required note: "reviewed
 * all the HPO choices, kept them" is what a later reader needs, and it is
 * the whole point of resolving in bulk rather than one by one. The dialog
 * says how many and from which agent, so a stale filter is caught here. */
import { useEffect, useState } from 'react'
import { CheckCheck } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Textarea } from '@/components/ui/textarea'

export function ResolveAllFlagsDialog({
  count,
  agentLabel,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: {
  count: number
  /** The agent the list is filtered to, or null for every agent. */
  agentLabel: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (note: string) => void
  isPending?: boolean
}) {
  const [note, setNote] = useState('')

  useEffect(() => {
    if (open) setNote('')
  }, [open])

  const what = `${count} open flag${count === 1 ? '' : 's'}${agentLabel ? ` from ${agentLabel}` : ''}`

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent onClick={(e) => e.stopPropagation()}>
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300">
            <CheckCheck />
          </AlertDialogMedia>
          <AlertDialogTitle>Resolve {what}</AlertDialogTitle>
          <AlertDialogDescription>
            Every flag currently listed gets this note and your name. A resolution cannot be reopened; a
            decision that turns out wrong is fixed by editing or deleting the row itself.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Textarea
          autoFocus
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What you decided about these and why..."
          maxLength={240}
          rows={3}
        />
        <AlertDialogFooter>
          <AlertDialogCancel variant="outline">Cancel</AlertDialogCancel>
          <AlertDialogAction disabled={!note.trim() || isPending} onClick={() => onConfirm(note.trim())}>
            {isPending ? 'Saving...' : `Resolve ${count}`}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
