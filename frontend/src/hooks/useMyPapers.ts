import { useQuery } from '@tanstack/react-query'
import { listPapersPapersGet } from '@/api/generated'
import type { PaperSummaryResp } from '@/api/generated/types.gen'
import { useAuth } from '@/lib/auth'

const STALE_TIME = 5 * 60 * 1000

/** Papers the signed-in user has touched, newest activity first.
 *
 * Keyed by user id so switching accounts cannot serve the previous user's list
 * from cache, and disabled until /auth/me resolves -- without an id there is no
 * query to make, and firing one unfiltered would fetch every paper.
 */
export function useMyPapers() {
  const { user } = useAuth()

  const query = useQuery({
    queryKey: ['papers', 'touched-by', user?.id],
    queryFn: () =>
      listPapersPapersGet({ query: { touched_by: user!.id } }) as Promise<
        unknown
      >,
    enabled: user?.id !== undefined,
    staleTime: STALE_TIME,
  })

  const papers = (Array.isArray(query.data) ? query.data : []) as PaperSummaryResp[]
  const sorted = [...papers].sort((a, b) =>
    (b.updated_at ?? '').localeCompare(a.updated_at ?? ''),
  )

  return {
    papers: sorted,
    isLoading: query.isPending && user?.id !== undefined,
    isError: query.isError,
    error: query.error,
  }
}
