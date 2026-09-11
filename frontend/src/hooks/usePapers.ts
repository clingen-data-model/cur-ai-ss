import { useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  listPaperCollaboratorsPapersCollaboratorsGet,
  listPapersPapersGet,
} from '@/api/generated'
import type { PaperSummaryResp, UserSummaryResp } from '@/api/generated/types.gen'
import { useAuth } from '@/lib/auth'
import type { IndexSearch } from '@/routeTree'

const STALE_TIME = 5 * 60 * 1000

/** Every paper, newest activity first, optionally narrowed to one person.
 *
 * Filtering happens in the database via `?touched_by=`, not in memory. At 94
 * papers either would do, but this is the shape that survives server-side
 * pagination: once the list is paginated, filtering a page you already hold is
 * wrong, and a client-side filter would have to be torn out. Doing it here
 * means only the query changes.
 *
 * Each filter is its own query key, so switching back to a scope you have
 * already viewed is served from cache rather than refetched, and the unfiltered
 * key matches useGeneTable's -- the genes tab and the unfiltered papers tab
 * share one response.
 */
export function usePapers(workedBy: IndexSearch['worked_by']) {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const targetId =
    workedBy === 'me' ? user?.id : typeof workedBy === 'number' ? workedBy : undefined

  // Same key as useGeneTable when unfiltered, so the two tabs share a response.
  const query = useQuery({
    queryKey: targetId === undefined ? ['papers'] : ['papers', { touched_by: targetId }],
    queryFn: () =>
      listPapersPapersGet(
        targetId === undefined ? {} : { query: { touched_by: targetId } },
      ),
    staleTime: STALE_TIME,
  })

  const papers = useMemo(() => {
    const rows = (Array.isArray(query.data) ? query.data : []) as PaperSummaryResp[]
    return [...rows].sort((a, b) =>
      (b.updated_at ?? '').localeCompare(a.updated_at ?? ''),
    )
  }, [query.data])

  // Its own endpoint rather than the collaborators present in the rows: the
  // options must be everyone who could narrow the list, and deriving them from
  // a filtered response would shrink the menu to whoever is already visible.
  // Server-side for the same reason the filter is -- enumerating collaborators
  // client-side would mean holding every paper.
  const peopleQuery = useQuery({
    queryKey: ['paper-collaborators'],
    queryFn: () => listPaperCollaboratorsPapersCollaboratorsGet(),
    staleTime: STALE_TIME,
  })
  const people = (
    Array.isArray(peopleQuery.data) ? peopleQuery.data : []
  ) as UserSummaryResp[]

  // Known only when the unfiltered response is already cached -- usually true,
  // since the genes tab populates that key. undefined otherwise, so the caller
  // can say "18 papers" rather than inventing "18 of 0".
  const cachedAll = queryClient.getQueryData<unknown>(['papers'])
  const total = Array.isArray(cachedAll) ? cachedAll.length : undefined

  return {
    papers,
    people,
    total,
    isLoading: query.isPending,
    isError: query.isError,
    error: query.error,
  }
}
