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
  [ReviewStatus.IN_PROGRESS]: 'In progress by',
  [ReviewStatus.COMPLETED]: 'Completed by',
}

/** Short form for a status-picker control, where the assignee is shown once. */
export const REVIEW_STATUS_SHORT_LABEL: Record<ReviewStatus, string> = {
  [ReviewStatus.NOT_ASSIGNED]: 'Not assigned',
  [ReviewStatus.ASSIGNED]: 'Assigned',
  [ReviewStatus.IN_PROGRESS]: 'In progress',
  [ReviewStatus.COMPLETED]: 'Completed',
}

/** "Not assigned" / "Assigned to Pat" / "In progress by Pat, Sam" /
 * "Completed by Pat +2": first names, and past two a count, so the badge
 * stays one table cell wide however many people share the paper. */
export function reviewStatusLabel(
  status: ReviewStatus,
  assignees: UserSummaryResp[] = [],
): string {
  const verb = REVIEW_STATUS_VERB[status]
  if (status === ReviewStatus.NOT_ASSIGNED || assignees.length === 0) return verb
  const names = assignees.map((a) => a.first_name || a.name)
  const shown = names.length > 2 ? `${names[0]} +${names.length - 1}` : names.join(', ')
  return `${verb} ${shown}`
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
