import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { REVIEW_STATES, REVIEW_STATE_LABEL, type ReviewState } from '@/lib/paperState'

const ANY = 'any'

function labelFor(state: string | null): string {
  if (state === null || state === ANY) return 'Any'
  return REVIEW_STATE_LABEL[state as ReviewState]
}

export function ReviewStatusFilter({
  value,
  onChange,
}: {
  value: ReviewState | undefined
  onChange: (next: ReviewState | undefined) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground whitespace-nowrap">Review Status</label>
      <Select
        value={value ?? ANY}
        onValueChange={(next: string | null) =>
          onChange(next === null || next === ANY ? undefined : (next as ReviewState))
        }
      >
        <SelectTrigger className="w-40">
          <SelectValue>{(state: string | null) => labelFor(state)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {REVIEW_STATES.map((state) => (
            <SelectItem key={state} value={state}>
              {labelFor(state)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
