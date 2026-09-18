/* Deterministic color for a pill in any multi-select field (Testing Methods
 * today, whatever else grows one later) -- not tied to a specific enum, so a
 * new multi-select gets colored pills for free.
 */
const PILL_COLORS = [
  'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200',
  'bg-blue-100 text-blue-900 dark:bg-blue-900/40 dark:text-blue-200',
  'bg-violet-100 text-violet-900 dark:bg-violet-900/40 dark:text-violet-200',
  'bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200',
  'bg-rose-100 text-rose-900 dark:bg-rose-900/40 dark:text-rose-200',
  'bg-cyan-100 text-cyan-900 dark:bg-cyan-900/40 dark:text-cyan-200',
  'bg-lime-100 text-lime-900 dark:bg-lime-900/40 dark:text-lime-200',
  'bg-fuchsia-100 text-fuchsia-900 dark:bg-fuchsia-900/40 dark:text-fuchsia-200',
  'bg-orange-100 text-orange-900 dark:bg-orange-900/40 dark:text-orange-200',
  'bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200',
  'bg-pink-100 text-pink-900 dark:bg-pink-900/40 dark:text-pink-200',
  'bg-teal-100 text-teal-900 dark:bg-teal-900/40 dark:text-teal-200',
  'bg-indigo-100 text-indigo-900 dark:bg-indigo-900/40 dark:text-indigo-200',
  'bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300',
]

/** djb2 -- cheap, stable across reloads, and doesn't need a hardcoded map
 * of every option a multi-select might ever have. */
function hashString(value: string): number {
  let hash = 5381
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 33) ^ value.charCodeAt(i)
  }
  return hash >>> 0
}

export function pillColorFor(value: string): string {
  return PILL_COLORS[hashString(value) % PILL_COLORS.length]
}
