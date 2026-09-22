/* A single-purpose "rerun this agent for this one row" button -- the scoped
 * counterpart to PaperActions.tsx's paper-wide RerunTaskButton, which always
 * queues a task unscoped (every instance of that type on the paper). Reused
 * by any section that has its own natural entity id to scope a rerun to
 * (variant, patient, family, ...), queuing the exact same
 * POST /papers/{paper_id}/tasks endpoint with that id set, so the task-queue
 * dedup/reset logic in enqueue_task applies exactly as it does for the
 * unscoped button. */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { RefreshCw } from 'lucide-react'
import { createTaskPapersPaperIdTasksPost } from '@/api/generated'
import type { TaskType } from '@/api/generated/types.gen'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { apiErrorMessage } from '@/lib/apiError'

interface TaskScope {
  family_id?: number
  patient_id?: number
  variant_id?: number
  phenotype_id?: number
  patient_variant_occurrence_id?: number
}

export function ScopedRerunButton({
  paperId,
  taskType,
  scope,
  label,
  description,
}: {
  paperId: number
  taskType: TaskType
  scope: TaskScope
  label: string
  description: string
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [context, setContext] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      createTaskPapersPaperIdTasksPost({
        path: { paper_id: paperId },
        body: {
          type: taskType,
          ...scope,
          additional_context: context.trim() || null,
          skip_successors: false,
        },
        throwOnError: true,
      }),
    onSuccess: () => {
      // Queuing a task changes the paper's status, which the papers table
      // renders -- without this it keeps reading Done until something else
      // happens to refetch it.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success(`${taskType} queued`)
      setOpen(false)
      setContext('')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to queue task')),
  })

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="gap-2">
        <RefreshCw className="size-3.5" />
        {label}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) setContext('')
        }}
      >
        <DialogContent onClick={(e) => e.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label>
              Additional context <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Textarea
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Any specific instructions for this run..."
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? 'Queuing...' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
