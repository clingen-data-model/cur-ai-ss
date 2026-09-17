/* A paper's state as a badge.
 *
 * Extracted from GeneTable when the papers table needed the same mapping, and
 * shared with the filter so the menu reads the same words as the column it
 * filters. The six API statuses are folded into four here -- see lib/paperState
 * for which, and why.
 */
import { Badge } from '@/components/ui/badge'
import { STATE_LABEL, STATE_OF, type PaperState } from '@/lib/paperState'
import type { VariantProps } from 'class-variance-authority'
import type { badgeVariants } from '@/components/ui/badge'
import type { PaperTaskStatus } from '@/api/generated/types.gen'

type BadgeVariant = VariantProps<typeof badgeVariants>['variant']

export const STATE_BADGE: Record<
  PaperState,
  { label: string; variant: BadgeVariant; className?: string }
> = {
  'not-started': { label: STATE_LABEL['not-started'], variant: 'secondary' },
  'in-progress': {
    label: STATE_LABEL['in-progress'],
    variant: 'outline',
    className: 'border-amber-500 text-amber-600',
  },
  done: {
    label: STATE_LABEL.done,
    variant: 'outline',
    className: 'border-green-500 text-green-600',
  },
  failed: { label: STATE_LABEL.failed, variant: 'destructive' },
}

/** The badge for a paper's API status, folded to its state. */
export function badgeFor(status: PaperTaskStatus) {
  return STATE_BADGE[STATE_OF[status]]
}

export function StatusBadge({ status }: { status: PaperTaskStatus }) {
  const { label, variant, className } = badgeFor(status)
  return (
    <Badge variant={variant} className={`${className ?? ''} hover:opacity-80 transition-opacity`}>
      {label}
    </Badge>
  )
}
