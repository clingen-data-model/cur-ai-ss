import { useEffect, useState } from 'react'

/** The current time, ticking once a second while `active`.
 *
 * Backs a live "12s" -> "1m 12s" counter next to a running task. Gated off
 * once nothing is running so a finished or idle paper doesn't keep a timer
 * alive for a number that will never change.
 */
export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!active) return
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [active, intervalMs])

  return now
}
