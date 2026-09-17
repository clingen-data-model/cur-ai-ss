import { useQuery } from '@tanstack/react-query'
import { listUsersUsersGet } from '@/api/generated'

const STALE_TIME = 5 * 60 * 1000

/** Every active account, for the review-assignee picker.
 *
 * Not usePapers' `people`: that list is scoped to people who have already
 * touched a paper, which is exactly wrong for assignment -- the point is to
 * be able to assign a paper to someone who has not worked on it yet.
 */
export function useUsers() {
  const query = useQuery({
    queryKey: ['users'],
    queryFn: () => listUsersUsersGet(),
    staleTime: STALE_TIME,
  })
  return { users: query.data ?? [], isLoading: query.isPending }
}
