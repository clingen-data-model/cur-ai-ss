import { useState } from 'react'

/** Holds a proposed value until a human edit note confirms or discards it.
 *
 * Wrapped in `{ value }` rather than storing `T` directly so a falsy proposed
 * value (`false`, `''`, `0`) doesn't get confused with "nothing pending".
 */
export function usePendingEdit<T>(onCommit: (value: T, note: string) => void) {
  const [pending, setPending] = useState<{ value: T } | null>(null)

  return {
    pendingValue: pending?.value,
    isOpen: pending !== null,
    propose: (value: T) => setPending({ value }),
    cancel: () => setPending(null),
    confirm: (note: string) => {
      if (pending) onCommit(pending.value, note)
      setPending(null)
    },
  }
}
