/* Narrows the papers table to one paper state.
 *
 * A plain select rather than the searchable combobox the person filter uses:
 * there are four states and they never grow with the data, so a search box
 * would be furniture. The person list can reach every account.
 *
 * Labels come from STATE_LABEL so the control reads the same words as the
 * column it filters. That applies to the closed trigger as well as the open
 * menu: Select.Value renders the raw value unless given a function, so without
 * labelFor below, picking "Done" left the trigger reading "done".
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PAPER_STATES, STATE_LABEL, type PaperState } from '@/lib/paperState'

const ANY = 'any'

function labelFor(state: string | null): string {
  if (state === null || state === ANY) return 'Any'
  return STATE_LABEL[state as PaperState]
}

export function ExtractionStatusFilter({
  value,
  onChange,
}: {
  value: PaperState | undefined
  onChange: (next: PaperState | undefined) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground whitespace-nowrap">Extraction Status</label>
      <Select
        value={value ?? ANY}
        onValueChange={(next: string | null) =>
          onChange(next === null || next === ANY ? undefined : (next as PaperState))
        }
      >
        <SelectTrigger className="w-40">
          <SelectValue>{(state: string | null) => labelFor(state)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {PAPER_STATES.map((state) => (
            <SelectItem key={state} value={state}>
              {labelFor(state)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
