/* Resolves a curator flag, once and for good. The note is required here
 * (the API allows none) for the same reason HumanEditNoteDialog forces one on
 * an edit: "looked at it, kept it" is the fact a later reader needs, and a
 * resolution cannot be reopened to add it afterwards. */
import { useEffect, useState } from 'react'
import { Flag } from 'lucide-react'
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
import type { FlagResp } from '@/api/generated/types.gen'

export function ResolveFlagDialog({
  flag,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: {
  flag: FlagResp | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (note: string) => void
  isPending?: boolean
}) {
  const [note, setNote] = useState('')

  useEffect(() => {
    if (open) setNote('')
  }, [open, flag?.id])

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent onClick={(e) => e.stopPropagation()}>
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300">
            <Flag />
          </AlertDialogMedia>
          <AlertDialogTitle>Resolve this flag</AlertDialogTitle>
          <AlertDialogDescription>
            Say what you decided about{' '}
            <span className="font-medium text-foreground">{flag?.subject}</span>. A resolution cannot be
            reopened; a decision that turns out wrong is fixed by editing or deleting the row itself.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Textarea
          autoFocus
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What you decided and why..."
          maxLength={240}
          rows={3}
        />
        <AlertDialogFooter>
          <AlertDialogCancel variant="outline">Cancel</AlertDialogCancel>
          <AlertDialogAction disabled={!note.trim() || isPending} onClick={() => onConfirm(note.trim())}>
            {isPending ? 'Saving...' : 'Resolve'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
