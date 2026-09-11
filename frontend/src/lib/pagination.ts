/** Marks a gap between page numbers in the output of `pageItems`. */
export const ELLIPSIS = 'ellipsis' as const

export type PageItem = number | typeof ELLIPSIS

/**
 * The page numbers to show, with gaps collapsed to an ellipsis.
 *
 * Zero-based in, one-based out: TanStack tracks `pageIndex` from 0 while the
 * control shows human page numbers.
 *
 * First and last are always present, so neither jump is ever more than one
 * click. The row is a constant `siblings * 2 + 5` items wide once there are
 * enough pages to need collapsing -- near the ends the window widens to fill
 * the slot the absent ellipsis frees, rather than letting the row shrink and
 * shift every button under the cursor while paging.
 */
export function pageItems(
  pageIndex: number,
  pageCount: number,
  siblings = 1,
): PageItem[] {
  if (pageCount < 1) return [1]

  const slots = siblings * 2 + 5
  if (pageCount <= slots) {
    return Array.from({ length: pageCount }, (_, i) => i + 1)
  }

  const current = pageIndex + 1
  // How many contiguous pages to show when anchored to either end: everything
  // except the far page and its ellipsis.
  const run = slots - 2

  if (current <= run - siblings) {
    const head = Array.from({ length: run }, (_, i) => i + 1)
    return [...head, ELLIPSIS, pageCount]
  }

  if (current >= pageCount - (run - siblings) + 1) {
    const tail = Array.from({ length: run }, (_, i) => pageCount - run + 1 + i)
    return [1, ELLIPSIS, ...tail]
  }

  const middle = Array.from(
    { length: siblings * 2 + 1 },
    (_, i) => current - siblings + i,
  )
  return [1, ELLIPSIS, ...middle, ELLIPSIS, pageCount]
}
