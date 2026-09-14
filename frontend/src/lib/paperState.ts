/* The paper states a curator can act on.
 *
 * The API reports six (lib/models/paper.py). Two of the distinctions are the
 * scheduler's bookkeeping rather than anything a person can do something about,
 * and reading them in a filter menu meant knowing how the queue works:
 *
 *   idle    no tasks exist yet
 *   pending tasks exist, none has begun
 *     -> the difference is whether a row has been written. Both mean nothing
 *        has happened to this paper.
 *
 *   running a handler is executing right now
 *   partial some tasks finished, none executing
 *     -> the difference is whether a worker happens to be mid-task at the
 *        instant you look. Both mean the paper is part-way through.
 *
 * Note that 'partial' was labelled "In progress" while meaning the opposite:
 * work started and stopped. Folding it in with 'running' is what makes that
 * label true.
 *
 * The six stay as they are server-side -- the task list and the pipeline view
 * are where that detail belongs, and the Streamlit UI reads them directly. This
 * is the summary the papers table and its filter speak in.
 */
import { PaperTaskStatus } from '@/api/generated/types.gen'
import type { PaperTaskStatus as PaperTaskStatusValue } from '@/api/generated/types.gen'

export type PaperState = 'not-started' | 'in-progress' | 'done' | 'failed'

/** In pipeline order, so the filter menu reads as a progression. */
export const PAPER_STATES: PaperState[] = [
  'not-started',
  'in-progress',
  'done',
  'failed',
]

export const STATE_OF: Record<PaperTaskStatusValue, PaperState> = {
  [PaperTaskStatus.IDLE]: 'not-started',
  [PaperTaskStatus.PENDING]: 'not-started',
  [PaperTaskStatus.RUNNING]: 'in-progress',
  [PaperTaskStatus.PARTIAL]: 'in-progress',
  [PaperTaskStatus.COMPLETED]: 'done',
  [PaperTaskStatus.FAILED]: 'failed',
}

export const STATE_LABEL: Record<PaperState, string> = {
  'not-started': 'Not started',
  'in-progress': 'In progress',
  done: 'Done',
  failed: 'Failed',
}

export function isPaperState(value: unknown): value is PaperState {
  return typeof value === 'string' && (PAPER_STATES as string[]).includes(value)
}
