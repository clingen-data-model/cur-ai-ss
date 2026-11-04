/* The curator sign-off stamp (lib/models/signoff.py) as a row marker: the
 * fourth entry in the row-icon language next to ManuallyCreatedIndicator
 * (orange: a human made this), EvidencePopover (grey: here is the evidence)
 * and FlagIndicator (violet: an agent asked for a look). Green check: a
 * curator confirmed this occurrence (the stamp lives on occurrences alone:
 * lib/models/signoff.py).
 */
import { CircleCheck, CircleCheckBig, CircleDashed } from 'lucide-react'
import type { UserSummaryResp } from '@/api/generated/types.gen'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export interface Stamped {
  reviewed_at?: string | null
  reviewed_by?: UserSummaryResp | null
}

export function isStamped(row: Stamped): boolean {
  return row.reviewed_at != null
}

export function stampText(row: Stamped): string {
  if (!isStamped(row)) return 'Not yet confirmed'
  const who = row.reviewed_by ? ` by ${row.reviewed_by.name}` : ''
  const when = row.reviewed_at ? ` on ${new Date(row.reviewed_at).toLocaleDateString()}` : ''
  return `Confirmed${who}${when}`
}

/** One marker for a set of stamped rows: all, some or none confirmed. */
export function SignoffMark({ rows, labels }: { rows: Stamped[]; labels?: string[] }) {
  const stamped = rows.filter(isStamped)
  if (rows.length === 0) return null
  const all = stamped.length === rows.length
  const none = stamped.length === 0
  const detail =
    rows.length === 1
      ? stampText(rows[0])
      : rows.map((row, index) => `${labels?.[index] ?? `Row ${index + 1}`}: ${stampText(row)}`).join('\n')
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span className="inline-flex items-center justify-center size-6" />}
        aria-label={detail}
      >
        {none ? (
          <CircleDashed className="size-3.5 text-muted-foreground/50" />
        ) : all ? (
          <CircleCheckBig className="size-3.5 text-green-600" />
        ) : (
          <CircleCheck className="size-3.5 text-amber-500" />
        )}
      </TooltipTrigger>
      <TooltipContent className="whitespace-pre-line text-left">
        {none ? 'Not yet confirmed' : all ? detail : `Partly confirmed\n${detail}`}
      </TooltipContent>
    </Tooltip>
  )
}
