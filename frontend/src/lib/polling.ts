/* One cadence for every list that shows the worker's progress.
 *
 * Polled queries are a real cost decision, so the number lives in one place.
 * The worker claims work every 5s (POLL_INTERVAL_S in lib/bin/worker.py), so
 * polling faster than that shows the same rows twice; and while nothing is in
 * flight there is nothing to be timely about, so the lists poll only while a
 * paper has a task going.
 */
import type { PaperSummaryResp } from '@/api/generated/types.gen'

export const POLL_WHILE_ACTIVE_MS = 5_000

/** Whether any paper in a list has a task in flight. Pending counts, not just
 * Running: a successor is created Pending the instant its predecessor
 * completes and only flips to Running on the worker's next poll, so a check
 * on Running alone can land in that gap and stop polling for good. */
export function anyPaperInFlight(papers: readonly PaperSummaryResp[] | undefined): boolean {
  return papers?.some((p) => p.status === 'running' || p.status === 'pending') ?? false
}

/** `refetchInterval` for a papers-list query: brisk while a paper is in
 * flight, off otherwise. Enqueueing a task invalidates ['papers'], so the
 * refetch that follows is what switches polling on. */
export function pollWhileInFlight(papers: readonly PaperSummaryResp[] | undefined): number | false {
  return anyPaperInFlight(papers) ? POLL_WHILE_ACTIVE_MS : false
}
