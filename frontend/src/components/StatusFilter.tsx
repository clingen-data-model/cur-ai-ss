/* Narrows the papers table to one pipeline status.
 *
 * A plain select rather than the searchable combobox the person filter uses:
 * there are six statuses and they never grow with the data, so a search box
 * would be furniture. The person list can reach every account.
 *
 * Labels come from STATUS_BADGE so the menu reads the same words as the column
 * it filters -- "Done", not "completed".
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { STATUS_BADGE } from '@/components/StatusBadge'
import { PaperTaskStatus } from '@/api/generated/types.gen'
import type { PaperTaskStatus as Status } from '@/api/generated/types.gen'

const ANY = 'any'

// Pipeline order, so the menu reads as a progression rather than alphabetically.
const ORDER: Status[] = [
  PaperTaskStatus.IDLE,
  PaperTaskStatus.PENDING,
  PaperTaskStatus.RUNNING,
  PaperTaskStatus.PARTIAL,
  PaperTaskStatus.COMPLETED,
  PaperTaskStatus.FAILED,
]

export function StatusFilter({
  value,
  onChange,
}: {
  value: Status | undefined
  onChange: (next: Status | undefined) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground whitespace-nowrap">Status</label>
      <Select
        value={value ?? ANY}
        onValueChange={(next: string | null) =>
          onChange(next === null || next === ANY ? undefined : (next as Status))
        }
      >
        <SelectTrigger className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any status</SelectItem>
          {ORDER.map((status) => (
            <SelectItem key={status} value={status}>
              {STATUS_BADGE[status].label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
