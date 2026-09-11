/* A paper's pipeline status as a badge.
 *
 * Extracted from GeneTable when the papers table needed the same mapping. The
 * keys are the API's PaperTaskStatus values, which are lowercase precisely so
 * the server's string indexes this map directly -- see lib/models/paper.py.
 */
import { Badge } from '@/components/ui/badge'
import type { VariantProps } from 'class-variance-authority'
import type { badgeVariants } from '@/components/ui/badge'
import type { PaperTaskStatus } from '@/api/generated/types.gen'

type BadgeVariant = VariantProps<typeof badgeVariants>['variant']

export const STATUS_BADGE: Record<
  PaperTaskStatus,
  { label: string; variant: BadgeVariant; className?: string }
> = {
  idle: { label: 'Not started', variant: 'secondary' },
  pending: { label: 'Pending', variant: 'secondary' },
  running: { label: 'Running', variant: 'default' },
  partial: {
    label: 'In progress',
    variant: 'outline',
    className: 'border-amber-500 text-amber-600',
  },
  completed: {
    label: 'Done',
    variant: 'outline',
    className: 'border-green-500 text-green-600',
  },
  failed: { label: 'Failed', variant: 'destructive' },
}

export function StatusBadge({ status }: { status: PaperTaskStatus }) {
  const { label, variant, className } = STATUS_BADGE[status]
  return (
    <Badge variant={variant} className={className}>
      {label}
    </Badge>
  )
}
