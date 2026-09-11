/* The people who have touched a paper, as an overlapping avatar group.
 *
 * Measured at most two collaborators per paper on dev, so the overflow count is
 * defensive rather than routine -- but the cell has to stay a fixed width in a
 * table column, so it caps rather than growing with the list.
 */
import { Avatar, AvatarFallback, AvatarGroup, AvatarGroupCount, AvatarImage } from '@/components/ui/avatar'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { initialsFor } from '@/components/UserAvatar'
import { API_BASE_URL } from '@/lib/api'
import type { UserSummaryResp } from '@/api/generated/types.gen'

const MAX_SHOWN = 3

export function Collaborators({ users }: { users: UserSummaryResp[] }) {
  if (users.length === 0) {
    // Two thirds of papers on dev have no human toucher at all -- an em dash
    // reads as "nobody yet" where an empty cell reads as a rendering bug.
    return <span className="text-muted-foreground">—</span>
  }

  const shown = users.slice(0, MAX_SHOWN)
  const hidden = users.slice(MAX_SHOWN)

  return (
    <AvatarGroup data-size="sm" className="justify-start">
      {shown.map((user) => (
        <Tooltip key={user.id}>
          <TooltipTrigger render={<span />}>
            <Avatar size="sm">
              <AvatarImage
                src={user.avatar_url ? `${API_BASE_URL}${user.avatar_url}` : undefined}
                alt={user.name}
              />
              <AvatarFallback>{initialsFor(user)}</AvatarFallback>
            </Avatar>
          </TooltipTrigger>
          <TooltipContent>{user.name}</TooltipContent>
        </Tooltip>
      ))}
      {hidden.length > 0 && (
        <Tooltip>
          <TooltipTrigger render={<span />}>
            <AvatarGroupCount>+{hidden.length}</AvatarGroupCount>
          </TooltipTrigger>
          {/* The overflow is the only way to see who these people are. */}
          <TooltipContent>{hidden.map((u) => u.name).join(', ')}</TooltipContent>
        </Tooltip>
      )}
    </AvatarGroup>
  )
}
