/* A compound-het pairing's confidence as a badge, next to the paired variant
 * in the Occurrences table -- the SPA analog of what Streamlit shows as a
 * confidence suffix on the "Paired Variant" column. Modeled on
 * StatusBadge.tsx's STATE_BADGE map.
 */
import { Badge } from '@/components/ui/badge'
import { CompoundHetConfidence } from '@/api/generated/types.gen'

const CONFIDENCE_BADGE: Record<CompoundHetConfidence, { label: string; className: string }> = {
  [CompoundHetConfidence.CONFIRMED]: {
    label: 'Confirmed',
    className: 'border-green-500 text-green-600',
  },
  [CompoundHetConfidence.ASSUMED]: {
    label: 'Assumed',
    className: 'border-amber-500 text-amber-600',
  },
  [CompoundHetConfidence.UNCERTAIN]: {
    label: 'Uncertain',
    className: 'border-muted-foreground text-muted-foreground',
  },
}

export function ConfidenceBadge({ confidence }: { confidence: CompoundHetConfidence }) {
  const { label, className } = CONFIDENCE_BADGE[confidence]
  return (
    <Badge variant="outline" className={className}>
      {label}
    </Badge>
  )
}
