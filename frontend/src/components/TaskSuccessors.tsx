/* What else a re-run sets in motion, as indented arrow rows -- shared by the
 * paper-wide Rerun Agent dialog (PaperActions.tsx) and every scoped re-run
 * button (ScopedRerunButton.tsx), so both show the same chain for the same
 * task. The edges come from GET /task-types, the worker's own dependency
 * table, so the display cannot drift from what actually gets queued.
 */
import { useQuery } from '@tanstack/react-query'
import { listTaskTypesTaskTypesGet } from '@/api/generated'
import type { TaskType, TaskTypeResp } from '@/api/generated/types.gen'

/** The pipeline's task types with descriptions and successors; fixed for the
 * life of a deploy, so fetched once and kept. */
export function useTaskTypes(enabled = true) {
  return useQuery({
    queryKey: ['task-types'],
    queryFn: () => listTaskTypesTaskTypesGet({ throwOnError: true }),
    staleTime: Infinity,
    enabled,
  })
}

/** The steps a re-run of `root` sets in motion, one row per depth. A step
 * sits at the longest path from the root, so it is listed after everything it
 * waits on: Extraction Verification, fed by every leaf, always lands last.
 * Within a row, pipeline order. */
export function successorLevels(root: TaskType, taskTypes: TaskTypeResp[]): TaskType[][] {
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

/** The chain a re-run of `taskType` triggers. `skipped` dims it rather than
 * hiding it, so "skip successors" is a choice about something visible. Renders
 * nothing until the task types have loaded. */
export function TaskSuccessors({ taskType, skipped = false }: { taskType: TaskType; skipped?: boolean }) {
  const taskTypes = useTaskTypes()
  if (!taskTypes.data) return null
  const describe = (t: TaskType) => taskTypes.data.find((row) => row.type === t)?.description
  const levels = successorLevels(taskType, taskTypes.data)
  if (levels.length === 0) {
    return <p className="text-xs text-muted-foreground">Nothing runs after this task.</p>
  }
  return (
    <div className={`text-xs ${skipped ? 'text-muted-foreground/50' : 'text-muted-foreground'}`}>
      <p>{skipped ? 'Would otherwise also run:' : 'Also runs, in turn:'}</p>
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
  )
}
