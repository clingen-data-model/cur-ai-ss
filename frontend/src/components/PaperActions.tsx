/* Per-paper actions: re-run an agent, delete the paper.
 *
 * Lifted out of GeneTable when the papers table needed the same two controls.
 * Nothing about them was card-specific -- both take a paper and render an icon
 * button -- so they moved unchanged rather than being reimplemented.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { RefreshCw, Trash2 } from 'lucide-react'
import {
  createTaskPapersPaperIdTasksPost,
  deletePaperPapersPaperIdDelete,
  getPaperPapersPaperIdGet,
  rerunAllPapersPaperIdRerunAllPost,
} from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogMedia, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import type { PaperSummaryResp, TaskType } from '@/api/generated/types.gen'
import { CONTEXT_NOTE, TaskSuccessors, useTaskTypes } from '@/components/TaskSuccessors'
import { usePaperBusy } from '@/hooks/usePaperBusy'
import { apiErrorMessage } from '@/lib/apiError'

/* The fields RerunTaskDialog actually needs -- narrower than PaperSummaryResp
 * so it can also take a PaperResp (the paper-detail page's shape, which has
 * no gene_symbol/status/thumbnail_url) without a fake/partial object. */
type RerunnablePaper = Pick<PaperSummaryResp, 'id' | 'title' | 'filename'>

// Every task type is rerunnable except 'General Paper Question', which is only
// ever created ad hoc by the chat router.
const RERUNNABLE_TASK_TYPES: TaskType[] = [
  'PDF Parsing', 'Paper Classifier', 'Paper Metadata',
  'Variant Extraction', 'Pedigree Description', 'Patient Extraction',
  'Patient Demographics',
  'Segregation Evidence Extraction', 'Segregation Analysis Computed',
  'Variant Harmonization', 'Variant Annotation', 'Patient Variant Occurrences',
  'Compound Het Evaluation',
  'Phenotype Extraction', 'HPO Linking', 'Paper MONDO Linking', 'Occurrence MONDO Linking',
  'Extraction Verification',
]

/* The dropdown's first entry: every task, from the top of the pipeline. It is
 * not a TaskType, so it never reaches the task endpoint -- it has its own
 * (POST /papers/{id}/rerun-all). */
const ALL_TASKS = 'All tasks'
type RerunChoice = TaskType | typeof ALL_TASKS

/** Under the box in "All tasks" mode; the per-task counterpart is CONTEXT_NOTE. */
const ALL_CONTEXT_NOTE =
  'Shown to every agent that reads the paper, on its fresh run, and kept on the paper for later runs. Replaces the previous notes; clear the box to remove them.'

/* Shared by RerunTaskButton's own trigger (papers table / gene cards) and the
 * "Re-run agents" button atop the task-timeline popovers -- same dialog
 * either way. Kept as one definition so the two triggers can't drift into
 * asking for different fields. */
function RerunTaskDialog({
  paper,
  open,
  onOpenChange,
  initialTaskType = 'PDF Parsing',
}: {
  paper: RerunnablePaper
  open: boolean
  onOpenChange: (open: boolean) => void
  initialTaskType?: TaskType
}) {
  const queryClient = useQueryClient()
  const [choice, setChoice] = useState<RerunChoice>(initialTaskType)
  const [skipSuccessors, setSkipSuccessors] = useState(false)
  const [reparsePdf, setReparsePdf] = useState(false)
  const [context, setContext] = useState('')
  const [contextTouched, setContextTouched] = useState(false)
  const allTasks = choice === ALL_TASKS
  const taskType = allTasks ? null : choice
  const busy = usePaperBusy(paper.id, open)
  // What each step is for, from the backend's own definition of the task types.
  const taskTypesQuery = useTaskTypes(open)
  const taskHelp = taskType
    ? taskTypesQuery.data?.find((t) => t.type === taskType)?.description
    : undefined

  // The notes already on the paper, so "All tasks" edits them in place rather
  // than starting from a blank box that would silently replace them.
  const notesQuery = useQuery({
    queryKey: ['paper-global-additional-context', paper.id],
    queryFn: () => getPaperPapersPaperIdGet({ path: { paper_id: paper.id }, throwOnError: true }),
    enabled: open && allTasks,
    select: (resp) => resp.paper_global_additional_context ?? '',
  })
  useEffect(() => {
    if (allTasks && !contextTouched && notesQuery.data !== undefined) setContext(notesQuery.data)
  }, [allTasks, contextTouched, notesQuery.data])

  const mutation = useMutation({
    mutationFn: () => taskType === null
      ? rerunAllPapersPaperIdRerunAllPost({
          path: { paper_id: paper.id },
          body: { reparse_pdf: reparsePdf, additional_context: context || null },
          throwOnError: true,
        })
      : createTaskPapersPaperIdTasksPost({
          path: { paper_id: paper.id },
          body: { type: taskType, skip_successors: skipSuccessors, additional_context: context || null },
          throwOnError: true,
        }),
    onSuccess: () => {
      // Queuing a task changes the paper's status, which both the cards and the
      // papers table render. Without this the badge keeps reading Done until
      // something else happens to refetch.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper-tasks', paper.id] })
      queryClient.invalidateQueries({ queryKey: ['paper-global-additional-context', paper.id] })
      queryClient.invalidateQueries({ queryKey: ['paper', paper.id] })
      toast.success(allTasks ? 'Re-running all tasks' : 'Task queued')
      onOpenChange(false)
      setContext('')
      setContextTouched(false)
      setSkipSuccessors(false)
      setReparsePdf(false)
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to queue task')),
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Re-opening (e.g. a different row's icon) should show that row's type,
        // not whatever was last picked from the dropdown.
        if (next) setChoice(initialTaskType)
        onOpenChange(next)
      }}
    >
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-semibold">Rerun Agent</h2>
            <p className="text-sm text-muted-foreground mt-0.5">{paper.title ?? paper.filename}</p>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Task</label>
            <Select value={choice} onValueChange={(v) => setChoice(v as RerunChoice)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              {/* Not aligned to the trigger: with the selected item pinned over
                  it, a short scrolling list floated up over the dialog and
                  showed a slice that did not include the selection. */}
              <SelectContent className="max-h-64" alignItemWithTrigger={false}>
                <SelectItem value={ALL_TASKS}>{ALL_TASKS}</SelectItem>
                {RERUNNABLE_TASK_TYPES.map(t => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {taskHelp && <p className="text-xs text-muted-foreground">{taskHelp}</p>}
            {allTasks && (
              <p className="text-xs text-muted-foreground">
                Every task, from the top of the pipeline, each agent starting fresh.
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">
              {allTasks ? 'Notes for every agent' : 'Additional context'}{' '}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <textarea
              value={context}
              onChange={(e) => {
                setContext(e.target.value)
                setContextTouched(true)
              }}
              placeholder={
                allTasks
                  ? 'Anything every agent should know about this paper...'
                  : 'Any specific instructions for this task run...'
              }
              rows={3}
              className="w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none resize-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <p className="text-xs text-muted-foreground">
              {allTasks ? ALL_CONTEXT_NOTE : CONTEXT_NOTE}
            </p>
          </div>
          {taskType === null ? (
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={reparsePdf}
                  onChange={(e) => setReparsePdf(e.target.checked)}
                  className="cursor-pointer"
                />
                Also re-parse the PDF
              </label>
              <p className="text-xs text-muted-foreground">
                Rebuilds the text, tables and images the agents cite. Off, the run starts at
                Paper Classifier and uses the parse already on disk.
              </p>
              <TaskSuccessors taskType={reparsePdf ? 'PDF Parsing' : 'Paper Classifier'} />
            </div>
          ) : (
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={skipSuccessors}
                  onChange={(e) => setSkipSuccessors(e.target.checked)}
                  className="cursor-pointer"
                />
                Skip successor tasks
              </label>
              {/* The dependency chain the checkbox cuts, so "skip" is a choice
               * about something visible. */}
              <TaskSuccessors taskType={taskType} skipped={skipSuccessors} />
            </div>
          )}
          {busy && <p className="text-sm text-amber-700 dark:text-amber-400">{busy}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !!busy}>
              {mutation.isPending ? 'Queuing...' : 'Confirm Rerun'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function RerunTaskButton({ paper }: { paper: PaperSummaryResp }) {
  const [open, setOpen] = useState(false)
  const isRunning = paper.status === 'running'

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
      <RerunTaskDialog paper={paper} open={open} onOpenChange={setOpen} />
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

export { RerunTaskButton, RerunTaskDialog, DeletePaperButton, RERUNNABLE_TASK_TYPES }
