/* Trashcan-icon-plus-confirmation control shared by every "delete this row"
 * action -- the same mechanism as DeletePaperButton, generalized so patients,
 * variants, and occurrences don't each reimplement the AlertDialog wiring. */
import { Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'
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
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

export function DeleteIconButton({
  title,
  description,
  onDelete,
  disabled,
}: {
  title: string
  description: ReactNode
  onDelete: () => void
  disabled?: boolean
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger
        type="button"
        disabled={disabled}
        onClick={(e) => e.stopPropagation()}
        className="flex items-center justify-center size-7 rounded text-destructive hover:bg-destructive/10 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Trash2 className="size-4" />
      </AlertDialogTrigger>
      <AlertDialogContent size="sm" onClick={(e) => e.stopPropagation()}>
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-destructive/10 text-destructive dark:bg-destructive/20">
            <Trash2 />
          </AlertDialogMedia>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel variant="outline">Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onDelete}>
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
