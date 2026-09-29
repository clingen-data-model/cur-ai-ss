import { useQuery } from '@tanstack/react-query'
import { listTasksPapersPaperIdTasksGet } from '@/api/generated'
import { paperBusyMessage } from '@/lib/taskState'

/** Whether a paper has tasks in flight, for disabling rerun controls with the
 * reason shown. Only fetches while `enabled` -- callers pass their dialog's
 * open state -- so a table of rows with rerun buttons polls nothing until one
 * is opened. Shares the ['paper-tasks', id] cache with the progress popover.
 *
 * A convenience, not the guard: POST /papers/{id}/tasks refuses with the same
 * message (409) whatever this says. */
export function usePaperBusy(paperId: number, enabled: boolean, action = 're-running') {
  const { data } = useQuery({
    queryKey: ['paper-tasks', paperId],
    queryFn: () =>
      listTasksPapersPaperIdTasksGet({ path: { paper_id: paperId }, throwOnError: true }),
    enabled,
    // Matches the worker's 10s claim cadence: the paper can go idle (or
    // busy) while the dialog sits open.
    refetchInterval: enabled ? 10_000 : false,
  })
  return data ? paperBusyMessage(data, action) : null
}
