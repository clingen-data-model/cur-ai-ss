/* The pill naming a flag's kind (Inferred, Conflict, ...), with the kind's
 * definition on hover. The six kinds are a closed list (FlagKind on the API
 * side); FLAG_KIND_LABELS carries the label and the one-line definition.
 */
import type { FlagResp } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { FLAG_KIND_LABELS, flagKindLabel } from '@/lib/flags'

export function FlagKindBadge({ flag, className }: { flag: Pick<FlagResp, 'kind'>; className?: string }) {
  const hint = FLAG_KIND_LABELS[flag.kind]?.hint
  const badge = (
    <Badge variant="outline" className={`font-normal text-muted-foreground ${className ?? ''}`}>
      {flagKindLabel(flag)}
    </Badge>
  )
  if (!hint) return badge
  return (
    <Tooltip>
      <TooltipTrigger render={badge} />
      <TooltipContent className="max-w-xs">{hint}</TooltipContent>
    </Tooltip>
  )
}
