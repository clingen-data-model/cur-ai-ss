import { useMemo } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  listPaperCollaboratorsPapersCollaboratorsGet,
  listPapersPapersGet,
} from '@/api/generated'
import type { PaperSummaryResp } from '@/api/generated/types.gen'
import { STATE_OF } from '@/lib/paperState'
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
export function usePapers(
  workedBy: IndexSearch['worked_by'],
  status?: IndexSearch['status'],
  review_status?: IndexSearch['review_status'],
  review_assignee?: IndexSearch['review_assignee'],
) {
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
    // Changing the filter changes the query key, so without this the new scope
    // starts out pending and the caller sees a load from scratch -- which blanked
    // the whole tab, including the control that had just been used. Holding the
    // previous rows keeps the page mounted while the new ones arrive; isFetching
    // is what says something is happening.
    placeholderData: keepPreviousData,
  })

  const papers = useMemo(() => {
    const rows = query.data ?? []
    // Status is filtered here rather than in the query, unlike touched_by.
    // It is computed per paper from that paper's tasks, not stored -- so the
    // server would have to derive every status before it could drop any, which
    // costs exactly what returning them all costs. touched_by is different: it
    // narrows the set of papers before their summaries are built.
    const matching = rows
      .filter((p) => (status ? STATE_OF[p.status] === status : true))
      .filter((p) => (review_status ? p.review_status === review_status : true))
      .filter((p) =>
        review_assignee !== undefined ? p.review_assignee?.id === review_assignee : true,
      )
    return [...matching].sort((a, b) =>
      (b.updated_at ?? '').localeCompare(a.updated_at ?? ''),
    )
  }, [query.data, status, review_status, review_assignee])

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
  const people = peopleQuery.data ?? []

  // Known only when the unfiltered response is already cached -- usually true,
  // since the genes tab populates that key. undefined otherwise, so the caller
  // can say "18 papers" rather than inventing "18 of 0".
  const cachedAll = queryClient.getQueryData<PaperSummaryResp[]>(['papers'])
  const total = cachedAll?.length

  // What the person filter alone returned, so the count can say "3 of 21" when
  // a status is also applied rather than jumping straight to the grand total.
  const beforeStatus = query.data?.length

  return {
    papers,
    people,
    total,
    beforeStatus,
    // isPending only, not isFetching: with placeholder data this is true just
    // once, on the very first load when there is genuinely nothing to show.
    isLoading: query.isPending,
    // A refresh in flight over rows already on screen -- worth a quiet hint,
    // never a spinner that replaces them.
    isRefreshing: query.isFetching && !query.isPending,
    isError: query.isError,
    error: query.error,
  }
}
