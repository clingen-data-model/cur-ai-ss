/* Curator sign-off (lib/models/signoff.py): the review walk's cases and the
 * stamp a confirm writes on each row of one.
 *
 * A stamp changes the occurrences' responses (reviewed_at/by), the paper's
 * progress (PaperResp.signoff and the papers list) and the cases themselves,
 * so one confirm invalidates all of them; the cases keep their order, the paper's own (see build_review_cases).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  getReviewCasesPapersPaperIdReviewCasesGet,
  signoffRowsPapersPaperIdSignoffPost,
} from '@/api/generated'
import type { ReviewCaseResp, SignoffRequest } from '@/api/generated/types.gen'
import { apiErrorMessage } from '@/lib/apiError'

export type { ReviewCaseResp }

const STALE_TIME = 5 * 60 * 1000

export function useReviewCases(paperId: number) {
  return useQuery({
    queryKey: ['review-cases', paperId],
    queryFn: () =>
      getReviewCasesPapersPaperIdReviewCasesGet({ path: { paper_id: paperId }, throwOnError: true }),
    staleTime: STALE_TIME,
  })
}

/** The occurrences a case stamps, as the request body names them. */
export function caseRows(reviewCase: ReviewCaseResp): Omit<SignoffRequest, 'confirmed'> {
  return { occurrence_ids: reviewCase.occurrence_ids }
}

export function useSignoff(paperId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SignoffRequest) =>
      signoffRowsPapersPaperIdSignoffPost({ path: { paper_id: paperId }, body, throwOnError: true }),
    onSuccess: (_progress, body) => {
      for (const key of ['review-cases', 'occurrences', 'paper']) {
        queryClient.invalidateQueries({ queryKey: [key, paperId] })
      }
      // The list's progress column and, if the paper just completed, its
      // review status.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      if (body.confirmed === false) toast.success('Confirmation taken back')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to save sign-off')),
  })
}
