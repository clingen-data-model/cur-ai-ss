import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listPapersPapersGet } from '@/api/generated'
import type { PaperSummaryResp, UserSummaryResp } from '@/api/generated/types.gen'
import { useAuth } from '@/lib/auth'
import type { IndexSearch } from '@/routeTree'

const STALE_TIME = 5 * 60 * 1000

/** Every paper, newest activity first, optionally narrowed to one person.
 *
 * Fetches the full list and filters in memory rather than refetching with
 * `?touched_by=`, for two reasons: the query key matches useGeneTable's, so the
 * genes tab and this one share a single cached response and switching between
 * them costs nothing; and changing the filter is then instant instead of a
 * round trip. At 94 papers the whole list is ~43 KB.
 *
 * The endpoint's `touched_by` is the escape hatch for when this list is large
 * enough to paginate server-side -- at which point filtering has to move back
 * to the database.
 */
export function usePapers(workedBy: IndexSearch['worked_by']) {
  const { user } = useAuth()

  const query = useQuery({
    queryKey: ['papers'],
    queryFn: () => listPapersPapersGet({}),
    staleTime: STALE_TIME,
  })

  const all = useMemo(() => {
    const papers = (Array.isArray(query.data) ? query.data : []) as PaperSummaryResp[]
    return [...papers].sort((a, b) =>
      (b.updated_at ?? '').localeCompare(a.updated_at ?? ''),
    )
  }, [query.data])

  // Only people who have actually touched something: an option that filters to
  // nothing is worse than no option, and this needs no users endpoint.
  const people = useMemo(() => {
    const byId = new Map<number, UserSummaryResp>()
    for (const paper of all) {
      for (const person of paper.collaborators ?? []) byId.set(person.id, person)
    }
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [all])

  const targetId =
    workedBy === 'me' ? user?.id : typeof workedBy === 'number' ? workedBy : undefined

  const papers = useMemo(
    () =>
      targetId === undefined
        ? all
        : all.filter((p) =>
            (p.collaborators ?? []).some((c) => c.id === targetId),
          ),
    [all, targetId],
  )

  return {
    papers,
    people,
    total: all.length,
    isLoading: query.isPending,
    isError: query.isError,
    error: query.error,
  }
}
