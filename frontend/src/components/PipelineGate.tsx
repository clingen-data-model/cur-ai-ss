/* Renders a section only once the agent that populates it has completed.
 *
 * Until then it explains which step is outstanding, so that an empty section is
 * never mistaken for a finished one. See lib/taskState.ts for why the task rows
 * are the only thing that can tell those apart.
 */
import { CircleAlert, Clock } from 'lucide-react'
import type { ReactNode } from 'react'
import type { TaskResp, TaskType } from '@/api/generated/types.gen'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Spinner } from '@/components/ui/spinner'
import { taskState, taskStateMessage, type TaskScope } from '@/lib/taskState'

export function PipelineGate({
  tasks,
  task,
  label,
  scope,
  children,
}: {
  tasks: TaskResp[]
  task: TaskType
  /** How to name the step in "<label> hasn't run yet". Defaults to the task's
   * own name, which reads as the agent rather than the curator's subject. */
  label?: string
  scope?: TaskScope
  children: ReactNode
}) {
  const state = taskState(tasks, task, scope)
  if (state === 'complete') return <>{children}</>

  const { title, description } = taskStateMessage(state, task, label)

  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          {state === 'running' ? (
            <Spinner />
          ) : state === 'failed' ? (
            <CircleAlert className="text-destructive" />
          ) : (
            <Clock />
          )}
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
