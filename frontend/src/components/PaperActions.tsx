/* Per-paper actions: re-run an agent, delete the paper.
 *
 * Lifted out of GeneTable when the papers table needed the same two controls.
 * Nothing about them was card-specific -- both take a paper and render an icon
 * button -- so they moved unchanged rather than being reimplemented.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { RefreshCw, Trash2 } from 'lucide-react'
import {
  createTaskPapersPaperIdTasksPost,
  deletePaperPapersPaperIdDelete,
  listTaskTypesTaskTypesGet,
} from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogMedia, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import type { PaperSummaryResp, TaskType, TaskTypeResp } from '@/api/generated/types.gen'
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

/** The steps a re-run of `root` sets in motion, one row per depth. A step
 * sits at the longest path from the root, so it is listed after everything it
 * waits on: Extraction Verification, fed by every leaf, always lands last.
 * Within a row, pipeline order. */
function successorLevels(root: TaskType, taskTypes: TaskTypeResp[]): TaskType[][] {
  const edges = new Map(taskTypes.map((t) => [t.type, t.successors]))
  const order = new Map(taskTypes.map((t, i) => [t.type, i]))
  const depth = new Map<TaskType, number>()
  const visit = (task: TaskType, d: number) => {
    for (const next of edges.get(task) ?? []) {
      if ((depth.get(next) ?? -1) < d) {
        depth.set(next, d)
        visit(next, d + 1)
      }
    }
  }
  visit(root, 0)
  const levels: TaskType[][] = []
  for (const [task, d] of depth) (levels[d] ??= []).push(task)
  return levels.map((level) => level.sort((a, b) => (order.get(a) ?? 0) - (order.get(b) ?? 0)))
}

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
  const [taskType, setTaskType] = useState<TaskType>(initialTaskType)
  const [skipSuccessors, setSkipSuccessors] = useState(false)
  const [context, setContext] = useState('')
  const busy = usePaperBusy(paper.id, open)
  // What each step is for, from the backend's own definition of the task types;
  // fixed for the life of a deploy, so fetched once.
  const taskTypesQuery = useQuery({
    queryKey: ['task-types'],
    queryFn: () => listTaskTypesTaskTypesGet({ throwOnError: true }),
    staleTime: Infinity,
    enabled: open,
  })
  const taskHelp = taskTypesQuery.data?.find((t) => t.type === taskType)?.description
  const describe = (t: TaskType) => taskTypesQuery.data?.find((row) => row.type === t)?.description
  const levels = taskTypesQuery.data ? successorLevels(taskType, taskTypesQuery.data) : []

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
      queryClient.invalidateQueries({ queryKey: ['paper-tasks', paper.id] })
      toast.success('Task queued')
      onOpenChange(false)
      setContext('')
      setSkipSuccessors(false)
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to queue task')),
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Re-opening (e.g. a different row's icon) should show that row's type,
        // not whatever was last picked from the dropdown.
        if (next) setTaskType(initialTaskType)
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
            <Select value={taskType} onValueChange={(v) => setTaskType(v as TaskType)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              {/* Not aligned to the trigger: with the selected item pinned over
                  it, a short scrolling list floated up over the dialog and
                  showed a slice that did not include the selection. */}
              <SelectContent className="max-h-64" alignItemWithTrigger={false}>
                {RERUNNABLE_TASK_TYPES.map(t => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {taskHelp && <p className="text-xs text-muted-foreground">{taskHelp}</p>}
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
            <p className="text-xs text-muted-foreground">
              Given to this task only, as a follow-up to its previous run. The tasks it triggers run fresh,
              without it.
            </p>
          </div>
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
            {/* What else this re-run sets in motion, a row per depth: the
             * dependency chain the checkbox cuts, so "skip" is a choice about
             * something visible. Dimmed, not hidden, when skipped. */}
            {taskTypesQuery.data &&
              (levels.length > 0 ? (
                <div className={`text-xs ${skipSuccessors ? 'text-muted-foreground/50' : 'text-muted-foreground'}`}>
                  <p>{skipSuccessors ? 'Would otherwise also run:' : 'Also runs, in turn:'}</p>
                  {levels.map((level, i) => (
                    <p key={i} style={{ paddingLeft: `${(i + 1) * 0.75}rem` }}>
                      <span aria-hidden>→ </span>
                      {level.map((t, j) => (
                        <span key={t} title={describe(t)}>
                          {j > 0 && ', '}
                          {t}
                        </span>
                      ))}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Nothing runs after this task.</p>
              ))}
          </div>
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
