/* The cadence of every query that follows the worker's progress.
 *
 * Polled queries are a real cost decision, so the number lives in one place.
 * The worker claims work every 5s (POLL_INTERVAL_S in lib/bin/worker.py), so
 * polling faster than that shows the same rows twice. GET /papers/active is
 * the one endpoint polled while nothing is open (see ActivityIndicator); the
 * full papers list is never polled, it is refreshed when the active set
 * changes.
 */
export const POLL_WHILE_ACTIVE_MS = 5_000
