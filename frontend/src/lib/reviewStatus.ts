/* A paper's review-workflow state, as words and a badge.
 *
 * Distinct from paperState.ts: that folds the *extraction* pipeline's six
 * statuses into four. This is the *review* workflow -- has a human signed off
 * -- which the API already reports as exactly four states, so there is
 * nothing to fold, just labels and colors to pick.
 */
import type { VariantProps } from 'class-variance-authority'
import type { badgeVariants } from '@/components/ui/badge'
import { ReviewStatus } from '@/api/generated/types.gen'
import type { UserSummaryResp } from '@/api/generated/types.gen'

type BadgeVariant = VariantProps<typeof badgeVariants>['variant']

export const REVIEW_STATUS_VERB: Record<ReviewStatus, string> = {
  [ReviewStatus.NOT_ASSIGNED]: 'Not assigned',
  [ReviewStatus.ASSIGNED]: 'Assigned to',
  [ReviewStatus.IN_PROGRESS]: 'In review by',
  [ReviewStatus.COMPLETED]: 'Completed by',
}

/** Short form for a status-picker control, where the assignee is shown once. */
export const REVIEW_STATUS_SHORT_LABEL: Record<ReviewStatus, string> = {
  [ReviewStatus.NOT_ASSIGNED]: 'Not assigned',
  [ReviewStatus.ASSIGNED]: 'Assigned',
  [ReviewStatus.IN_PROGRESS]: 'In review',
  [ReviewStatus.COMPLETED]: 'Completed',
}

/** "Not assigned" / "Assigned to Pat" / "In review by Pat" / "Completed by Pat". */
export function reviewStatusLabel(
  status: ReviewStatus,
  assignee?: UserSummaryResp | null,
): string {
  const verb = REVIEW_STATUS_VERB[status]
  if (status === ReviewStatus.NOT_ASSIGNED || !assignee) return verb
  return `${verb} ${assignee.first_name || assignee.name}`
}

export const REVIEW_STATUS_BADGE: Record<
  ReviewStatus,
  { variant: BadgeVariant; className?: string }
> = {
  [ReviewStatus.NOT_ASSIGNED]: { variant: 'secondary' },
  [ReviewStatus.ASSIGNED]: {
    variant: 'outline',
    className: 'border-blue-500 text-blue-600',
  },
  [ReviewStatus.IN_PROGRESS]: {
    variant: 'outline',
    className: 'border-amber-500 text-amber-600',
  },
  [ReviewStatus.COMPLETED]: {
    variant: 'outline',
    className: 'border-green-500 text-green-600',
  },
}
