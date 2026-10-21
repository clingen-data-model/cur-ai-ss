/* Per-paper actions: re-run an agent, delete the paper.
 *
 * Lifted out of GeneTable when the papers table needed the same two controls.
 * Nothing about them was card-specific -- both take a paper and render an icon
 * button -- so they moved unchanged rather than being reimplemented.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { RefreshCw, Trash2 } from 'lucide-react'
import {
  createTaskPapersPaperIdTasksPost,
  deletePaperPapersPaperIdDelete,
  rerunAllPapersPaperIdRerunAllPost,
} from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogMedia, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import type { PaperSummaryResp, TaskType } from '@/api/generated/types.gen'
import { CONTEXT_NOTE, TaskSuccessors, useTaskTypes } from '@/components/TaskSuccessors'
import { usePaperBusy } from '@/hooks/usePaperBusy'
import { apiErrorMessage } from '@/lib/apiError'

/* The fields RerunTaskDialog actually needs -- narrower than PaperSummaryResp
 * so it can also take a PaperResp (the paper-detail page's shape, which has
 * no gene_symbol/status/thumbnail_url) without a fake/partial object. */
type RerunnablePaper = Pick<
  PaperSummaryResp,
  'id' | 'title' | 'filename' | 'paper_global_additional_context'
>

// Every task type is rerunnable except 'General Paper Question', which is only
// ever created ad hoc by the chat router.
const RERUNNABLE_TASK_TYPES: TaskType[] = [
  'PDF Parsing', 'Paper Classifier', 'Paper Metadata',
  'Variant Extraction', 'Figure Description', 'Patient Extraction',
  'Patient Demographics',
  'Segregation Evidence Extraction', 'Segregation Analysis Computed',
  'Variant Harmonization', 'Variant Annotation', 'Patient Variant Occurrences',
  'Compound Het Evaluation',
  'Phenotype Extraction', 'HPO Linking', 'Paper MONDO Linking', 'Occurrence MONDO Linking',
  'Extraction Verification',
]

/* The dialog's two tabs. "All tasks" is not a TaskType, so it never reaches
 * the task endpoint -- it has its own (POST /papers/{id}/rerun-all). */
type RerunTab = 'single' | 'all'

/** Under the "All tasks" box; the per-task counterpart is CONTEXT_NOTE. */
const GLOBAL_CONTEXT_NOTE =
  'Shown to every agent on its fresh run, and kept on the paper for later runs. Replaces the previous context; clear the box to remove it.'

/** Agents read all of it and skip what is not about their task, so a line
 * that opens with the task's name tells the right one it is meant for it. */
const GLOBAL_CONTEXT_HINT =
  'If an instruction is for one task, start it with that task\u2019s name, e.g. \u201cHPO Linking: treat all seizures as febrile.\u201d'

const TEXTAREA_CLASS =
  'w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none resize-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'

/* Shared by RerunTaskButton's own trigger (papers table / gene cards) and the
 * "Re-run agents" button atop the task-timeline popovers -- same dialog
 * either way. Kept as one definition so the two triggers can't drift into
 * asking for different fields. Two tabs: one task (with its own follow-up
 * context) or every task (with context global to the paper). */
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
  const [tab, setTab] = useState<RerunTab>('single')
  const [taskType, setTaskType] = useState<TaskType>(initialTaskType)
  const [skipSuccessors, setSkipSuccessors] = useState(false)
  const [context, setContext] = useState('')
  const [reparsePdf, setReparsePdf] = useState(false)
  const [globalContext, setGlobalContext] = useState('')
  const allTab = tab === 'all'
  const busy = usePaperBusy(paper.id, open)
  // What each step is for, from the backend's own definition of the task types.
  const taskTypesQuery = useTaskTypes(open)
  const taskHelp = taskTypesQuery.data?.find((t) => t.type === taskType)?.description

  // Opening the dialog starts from what the paper already holds, whichever
  // trigger opened it, so the All tasks tab edits the global context in place
  // rather than starting from a blank box that would silently replace it. It
  // comes off the paper row the caller already has: no request of its own.
  useEffect(() => {
    if (!open) return
    setTab('single')
    setTaskType(initialTaskType)
    setGlobalContext(paper.paper_global_additional_context ?? '')
    // Only when the dialog opens: a refetch of the paper while it is open
    // must not overwrite what the curator has typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const mutation = useMutation({
    mutationFn: () => allTab
      ? rerunAllPapersPaperIdRerunAllPost({
          path: { paper_id: paper.id },
          body: { reparse_pdf: reparsePdf, additional_context: globalContext || null },
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
      queryClient.invalidateQueries({ queryKey: ['paper', paper.id] })
      toast.success(allTab ? 'Re-running all tasks' : 'Task queued')
      onOpenChange(false)
      setContext('')
      setSkipSuccessors(false)
      setReparsePdf(false)
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to queue task')),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-semibold">Rerun Agent</h2>
            <p className="text-sm text-muted-foreground mt-0.5">{paper.title ?? paper.filename}</p>
          </div>
          <Tabs value={tab} onValueChange={(v) => setTab(v as RerunTab)}>
            <TabsList className="w-full">
              <TabsTrigger value="single">Single task</TabsTrigger>
              <TabsTrigger value="all">All tasks</TabsTrigger>
            </TabsList>
            <TabsContent value="single" className="space-y-4 pt-2">
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
                  className={TEXTAREA_CLASS}
                />
                <p className="text-xs text-muted-foreground">{CONTEXT_NOTE}</p>
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
                {/* The dependency chain the checkbox cuts, so "skip" is a choice
                 * about something visible. */}
                <TaskSuccessors taskType={taskType} skipped={skipSuccessors} />
              </div>
            </TabsContent>
            <TabsContent value="all" className="space-y-4 pt-2">
              <p className="text-xs text-muted-foreground">
                Re-runs every task from the top of the pipeline, each agent starting fresh.
              </p>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">
                  Context for every agent <span className="text-muted-foreground font-normal">(optional)</span>
                </label>
                <textarea
                  value={globalContext}
                  onChange={(e) => setGlobalContext(e.target.value)}
                  placeholder="Anything every agent should know, or Task name: an instruction for one task..."
                  rows={3}
                  className={TEXTAREA_CLASS}
                />
                <p className="text-xs text-muted-foreground">{GLOBAL_CONTEXT_HINT}</p>
                <p className="text-xs text-muted-foreground">{GLOBAL_CONTEXT_NOTE}</p>
              </div>
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
              </div>
            </TabsContent>
          </Tabs>
          {busy && <p className="text-sm text-amber-700 dark:text-amber-400">{busy}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !!busy}>
              {mutation.isPending ? 'Queuing...' : allTab ? 'Confirm Rerun All' : 'Confirm Rerun'}
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
