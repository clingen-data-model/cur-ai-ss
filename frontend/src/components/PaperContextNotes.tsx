/* The paper's Additional context, shared by every dialog that queues a run:
 * the paper-wide re-run dialog (PaperActions.tsx), the per-row ones
 * (ScopedRerunButton, RelinkHpoDialog, PairOccurrenceDialog) and a flag's
 * re-run (RerunFromFlagDialog). The context is a list of notes, one per
 * instruction a curator gave, each labelled with the step and row it was
 * given for and by whom; every agent reads every note on every run, until a
 * curator removes it here. The box below the list adds one, anchored by the
 * server to whatever the dialog is about to run. The list rather than one
 * editable text: a text gave no way to see what each paragraph was for, or
 * to take one out without retyping the rest. A task has no context of its
 * own: it used to, as a follow-up to that task's last run, and a curator who
 * picked the wrong task left the right agent unaware of it. */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { X } from 'lucide-react'
import { deleteContextNotePapersPaperIdContextNotesNoteIdDelete } from '@/api/generated'
import type { PaperContextNoteResp } from '@/api/generated/types.gen'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { apiErrorMessage } from '@/lib/apiError'

const SOURCE_LABEL: Record<PaperContextNoteResp['source'], string> = {
  curator: 'Re-run',
  flag: 'Flag re-run',
  chat: 'Chat',
}

/** What the server labels a note with when it is given to every task. */
export const EVERY_TASK = 'All tasks'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function authorOf(note: PaperContextNoteResp) {
  const user = note.created_by
  if (!user) return null
  return `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim() || user.email
}

export function useRemoveContextNote(paperId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (noteId: number) =>
      deleteContextNotePapersPaperIdContextNotesNoteIdDelete({
        path: { paper_id: paperId, note_id: noteId },
        throwOnError: true,
      }),
    onSuccess: () => {
      // Both carry the notes: the paper page's query and the list rows the
      // paper-wide dialog opens from.
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to remove the note')),
  })
}

export function PaperContextNotes({
  paperId,
  notes,
  value,
  onChange,
  addLabel = 'Add context',
  addPlaceholder = 'Anything the agents should know for this run...',
  addHelp,
  disabled = false,
}: {
  paperId: number
  /** undefined while the paper is still loading. */
  notes: PaperContextNoteResp[] | undefined
  value: string
  onChange: (value: string) => void
  addLabel?: string
  addPlaceholder?: string
  /** Under the box: what the server will label this note with. */
  addHelp: string
  disabled?: boolean
}) {
  const remove = useRemoveContextNote(paperId)
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label>Additional context</Label>
        {notes === undefined ? (
          <p className="text-xs text-muted-foreground">Loading...</p>
        ) : notes.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            None yet. Every agent reads every note here on every run, until it is removed.
          </p>
        ) : (
          <ul className="divide-y rounded-md border text-sm">
            {notes.map((note) => {
              const author = authorOf(note)
              return (
                <li key={note.id} className="flex items-start gap-2 px-2.5 py-2">
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{note.anchor ?? EVERY_TASK}</span>
                      {' · '}
                      {SOURCE_LABEL[note.source]}
                      {author && ` · ${author}`}
                      {' · '}
                      {formatDate(note.created_at)}
                    </p>
                    <p className="whitespace-pre-wrap break-words">{note.text}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label="Remove note"
                    title="Remove: no later run will read it"
                    disabled={disabled || remove.isPending}
                    onClick={() => remove.mutate(note.id)}
                  >
                    <X />
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
      <div className="space-y-1.5">
        <Label>
          {addLabel} <span className="text-muted-foreground font-normal">(optional)</span>
        </Label>
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={addPlaceholder}
          rows={3}
          disabled={disabled}
        />
        <p className="text-xs text-muted-foreground">{addHelp}</p>
      </div>
    </div>
  )
}
