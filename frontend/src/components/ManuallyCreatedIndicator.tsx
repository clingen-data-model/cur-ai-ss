/* Row-level "created from scratch by a curator" marker -- the entity-level
 * analog of EvidencePopover's per-field manual-edit icon. Reuses the exact
 * same visual language (orange UserRoundPen, orange tooltip) so "orange
 * means human-touched" stays one convention across the app rather than two.
 *
 * created_by_user_id (not updated_by_user_id) is the signal: it's set once
 * at creation and never touched again, so it survives later edits -- unlike
 * updated_by_user_id, which gets overwritten by any edit and so can't tell
 * "curator-created" apart from "pipeline-created, later edited."
 */
import { UserRoundPen } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { UserSummaryResp } from '@/api/generated/types.gen'

interface ManuallyCreatedSource {
  label: string
  createdByUserId: number | null | undefined
  createdBy: UserSummaryResp | null | undefined
}

export function ManuallyCreatedIndicator({ sources }: { sources: ManuallyCreatedSource[] }) {
  const created = sources.filter((s) => s.createdByUserId != null)
  if (created.length === 0) return null

  return (
    <Tooltip>
      <TooltipTrigger render={<span className="inline-flex items-center cursor-help" />}>
        <UserRoundPen className="size-3.5 text-orange-500" />
      </TooltipTrigger>
      <TooltipContent className="bg-orange-500 text-white" arrowClassName="bg-orange-500 fill-orange-500">
        {created
          .map((s) => `${s.label} manually created${s.createdBy ? ` by ${s.createdBy.name}` : ''}`)
          .join('; ')}
      </TooltipContent>
    </Tooltip>
  )
}
