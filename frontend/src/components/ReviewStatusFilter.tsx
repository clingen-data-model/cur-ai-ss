import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  REVIEW_STATES,
  REVIEW_STATE_LABEL,
  reviewFilterAssigneeId,
  type ReviewFilterValue,
} from '@/lib/paperState'
import { useUsers } from '@/hooks/useUsers'
import type { UserSummaryResp } from '@/api/generated/types.gen'

const ANY = 'any'

function labelFor(state: string | null, users: UserSummaryResp[]): string {
  if (state === null || state === ANY) return 'Any'
  const assigneeId = reviewFilterAssigneeId(state as ReviewFilterValue)
  if (assigneeId !== undefined) {
    const user = users.find((u) => u.id === assigneeId)
    return user ? `Assigned to ${user.name}` : 'Assigned to…'
  }
  return REVIEW_STATE_LABEL[state as (typeof REVIEW_STATES)[number]]
}

export function ReviewStatusFilter({
  value,
  onChange,
}: {
  value: ReviewFilterValue | undefined
  onChange: (next: ReviewFilterValue | undefined) => void
}) {
  const { users } = useUsers()

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground whitespace-nowrap">Review Status</label>
      <Select
        value={value ?? ANY}
        onValueChange={(next: string | null) =>
          onChange(next === null || next === ANY ? undefined : (next as ReviewFilterValue))
        }
      >
        <SelectTrigger className="w-48">
          <SelectValue>{(state: string | null) => labelFor(state, users)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {REVIEW_STATES.map((state) => (
            <SelectItem key={state} value={state}>
              {REVIEW_STATE_LABEL[state]}
            </SelectItem>
          ))}
          {users.length > 0 && <SelectSeparator />}
          {users.map((user) => (
            <SelectItem key={user.id} value={`assigned_to:${user.id}`}>
              Assigned to {user.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
