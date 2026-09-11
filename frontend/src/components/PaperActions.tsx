/* Per-paper actions: re-run an agent, delete the paper.
 *
 * Lifted out of GeneTable when the papers table needed the same two controls.
 * Nothing about them was card-specific -- both take a paper and render an icon
 * button -- so they moved unchanged rather than being reimplemented.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { RefreshCw, Trash2 } from 'lucide-react'
import { createTaskPapersPaperIdTasksPost, deletePaperPapersPaperIdDelete } from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogMedia, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import type { PaperSummaryResp, TaskType } from '@/api/generated/types.gen'

// Every task type is rerunnable except 'General Paper Question', which is only
// ever created ad hoc by the chat router. Mirrors lib/ui/paper/header.py.
const RERUNNABLE_TASK_TYPES: TaskType[] = [
  'PDF Parsing', 'Paper Classifier', 'Paper Metadata',
  'Variant Extraction', 'Pedigree Description', 'Patient Extraction',
  'Patient Demographics',
  'Segregation Evidence Extraction', 'Segregation Analysis Computed',
  'Variant Harmonization', 'Variant Annotation', 'Patient Variant Occurrences',
  'Compound Het Evaluation',
  'Phenotype Extraction', 'HPO Linking', 'MONDO Linking',
]

function RerunTaskButton({ paper }: { paper: PaperSummaryResp }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [taskType, setTaskType] = useState<TaskType>('PDF Parsing')
  const [skipSuccessors, setSkipSuccessors] = useState(false)
  const [context, setContext] = useState('')
  const isRunning = paper.status === 'running'

  const mutation = useMutation({
    mutationFn: () => createTaskPapersPaperIdTasksPost({
      path: { paper_id: paper.id },
      body: { type: taskType, skip_successors: skipSuccessors, additional_context: context || null },
      throwOnError: true,
    }),
    onSuccess: () => {
      // Queuing a task changes the paper's status, which both the cards and the
      // papers table render. Without this the badge keeps reading Done until
      // something else happens to refetch.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Task queued')
      setOpen(false)
      setContext('')
      setSkipSuccessors(false)
    },
    onError: () => toast.error('Failed to queue task'),
  })

  return (
    <>
      <button
        type="button"
        disabled={!!isRunning}
        onClick={() => setOpen(true)}
        className="flex items-center justify-center size-7 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <RefreshCw className="size-4" />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold">Rerun Agent</h2>
              <p className="text-sm text-muted-foreground mt-0.5">{paper.title ?? paper.filename}</p>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Task</label>
              <Select value={taskType} onValueChange={(v) => setTaskType(v as TaskType)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-40">
                  {RERUNNABLE_TASK_TYPES.map(t => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">
                Additional context <span className="text-muted-foreground font-normal">(optional)</span>
              </label>
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="Any specific instructions for this task run..."
                rows={3}
                className="w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none resize-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                checked={skipSuccessors}
                onChange={(e) => setSkipSuccessors(e.target.checked)}
                className="cursor-pointer"
              />
              Skip successor tasks
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
                {mutation.isPending ? 'Queuing...' : 'Confirm Rerun'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function DeletePaperButton({ paper }: { paper: PaperSummaryResp }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => deletePaperPapersPaperIdDelete({ path: { paper_id: paper.id }, throwOnError: true }),
    onSuccess: () => {
      toast.success(`"${paper.title ?? paper.filename}" deleted`)
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: () => toast.error('Failed to delete paper'),
  })

  return (
    <AlertDialog>
      <AlertDialogTrigger
        type="button"
        className="flex items-center justify-center size-7 rounded text-destructive hover:bg-destructive/10 cursor-pointer transition-colors"
      >
        <Trash2 className="size-4" />
      </AlertDialogTrigger>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-destructive/10 text-destructive dark:bg-destructive/20">
            <Trash2 />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete paper?</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete <span className="font-medium text-foreground">{paper.title ?? paper.filename}</span> and all extracted data. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel variant="outline">Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => mutation.mutate()}>Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export { RerunTaskButton, DeletePaperButton, RERUNNABLE_TASK_TYPES }
