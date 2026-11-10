/* A paper's review status and assignees, editable inline from the table cell.
 *
 * Popover rather than a dialog: this is a two-field edit (who, and how far
 * along), which a click-to-open menu handles without leaving the table the
 * way the rerun/delete dialogs need to for a destructive or multi-field
 * action.
 *
 * A paper can be assigned to several people, who share its one status: each
 * name in the list is a toggle, and the menu stays open while names are
 * ticked so a second person does not cost a second trip.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check, UserX } from 'lucide-react'
import { updatePaperReviewPapersPaperIdReviewPatch } from '@/api/generated'
import { ReviewStatus } from '@/api/generated/types.gen'
import type { PaperSummaryResp, UserSummaryResp } from '@/api/generated/types.gen'
import { useUsers } from '@/hooks/useUsers'
import { useAuth } from '@/lib/auth'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { UserAvatar } from '@/components/UserAvatar'
import { REVIEW_STATUS_BADGE, REVIEW_STATUS_SHORT_LABEL, reviewStatusLabel } from '@/lib/reviewStatus'

/** Statuses selectable once a paper has an assignee, in workflow order. */
const IN_PROGRESS_STATUSES = [
  ReviewStatus.ASSIGNED,
  ReviewStatus.IN_PROGRESS,
  ReviewStatus.COMPLETED,
] as const

export function ReviewStatusBadge({
  status,
  assignees = [],
}: {
  status: ReviewStatus
  assignees?: UserSummaryResp[]
}) {
  const { variant, className } = REVIEW_STATUS_BADGE[status]
  return (
    <Badge
      variant={variant}
      className={className}
      // The label abbreviates past two people; the full list is here.
      title={assignees.length > 1 ? assignees.map((a) => a.name).join(', ') : undefined}
    >
      {reviewStatusLabel(status, assignees)}
    </Badge>
  )
}

/** Narrower than PaperSummaryResp so a PaperResp (the paper-detail page's
 * shape) satisfies it directly too -- both models carry these same three
 * fields with the same (optional) types. Mirrors PaperProgressPopover's
 * ProgressPaper. */
type ReviewablePaper = Pick<PaperSummaryResp, 'id' | 'review_status' | 'review_assignees'>

export function ReviewStatusCell({ paper }: { paper: ReviewablePaper }) {
  const { users } = useUsers()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  // Both default to their "nothing assigned yet" value: the API always sends
  // them, but the generated type treats server-defaulted fields as optional.
  const status = paper.review_status ?? ReviewStatus.NOT_ASSIGNED
  const assignees = paper.review_assignees ?? []
  const assigneeIds = assignees.map((a) => a.id)

  const mutation = useMutation({
    mutationFn: (body: { review_status: ReviewStatus; assignee_user_ids: number[] }) =>
      updatePaperReviewPapersPaperIdReviewPatch({
        path: { paper_id: paper.id },
        body,
        throwOnError: true,
      }),
    // The papers list and the paper-detail page (['paper', id]) both embed
    // review_status/review_assignees now, so both need invalidating.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', paper.id] })
    },
    onError: () => toast.error('Failed to update review status'),
  })

  /** Put a person on the paper or take them off. The status is the paper's,
   * not the person's, so it only moves at the ends: the first assignee makes
   * an unassigned paper Assigned, the last one leaving makes it Not assigned,
   * and anyone joining or leaving in between keeps it where it is. */
  const toggle = (userId: number) => {
    // The next set is built from the last response, so a second tick before
    // the first has come back would send a list without it.
    if (mutation.isPending) return
    const next = assigneeIds.includes(userId)
      ? assigneeIds.filter((id) => id !== userId)
      : [...assigneeIds, userId]
    mutation.mutate({
      review_status:
        next.length === 0
          ? ReviewStatus.NOT_ASSIGNED
          : status === ReviewStatus.NOT_ASSIGNED
            ? ReviewStatus.ASSIGNED
            : status,
      assignee_user_ids: next,
    })
  }

  const unassign = () => {
    mutation.mutate({ review_status: ReviewStatus.NOT_ASSIGNED, assignee_user_ids: [] })
    setOpen(false)
  }

  const setStatus = (review_status: ReviewStatus) => {
    if (assigneeIds.length === 0) return
    mutation.mutate({ review_status, assignee_user_ids: assigneeIds })
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className="cursor-pointer rounded focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        <ReviewStatusBadge status={status} assignees={assignees} />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0 gap-0">
        {/* Every item that reacts to typing -- status changes and the
            assignee list -- must live inside one <Command>: cmdk's
            sub-components (CommandSeparator included) read from context
            the root provides, and crash if rendered as its sibling. */}
        <Command>
          <CommandInput placeholder="Assign reviewer..." />
          <CommandList>
            <CommandEmpty>No one by that name.</CommandEmpty>
            {user && (
              <>
                <CommandGroup>
                  <CommandItem
                    value="Assign to me"
                    onSelect={() => toggle(user.id)}
                  >
                    <Check className={assigneeIds.includes(user.id) ? 'ml-auto size-4' : 'opacity-0'} />
                    Assign to me
                  </CommandItem>
                </CommandGroup>
                <CommandSeparator />
              </>
            )}
            {status !== ReviewStatus.NOT_ASSIGNED && (
              <>
                <CommandGroup heading="Status">
                  {IN_PROGRESS_STATUSES.map((s) => (
                    <CommandItem
                      key={s}
                      value={REVIEW_STATUS_SHORT_LABEL[s]}
                      onSelect={() => setStatus(s)}
                    >
                      {REVIEW_STATUS_SHORT_LABEL[s]}
                      {status === s && <Check className="ml-auto size-4" />}
                    </CommandItem>
                  ))}
                  <CommandItem
                    value="Unassign"
                    onSelect={unassign}
                    className="text-muted-foreground"
                  >
                    <UserX />
                    {assignees.length > 1 ? 'Unassign everyone' : 'Unassign'}
                  </CommandItem>
                </CommandGroup>
                <CommandSeparator />
              </>
            )}
            <CommandGroup heading="Assignees">
              {users.map((user) => (
                <CommandItem
                  key={user.id}
                  value={user.name}
                  onSelect={() => toggle(user.id)}
                >
                  <UserAvatar user={user} size="sm" />
                  {user.name}
                  {assigneeIds.includes(user.id) && <Check className="ml-auto size-4" />}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
