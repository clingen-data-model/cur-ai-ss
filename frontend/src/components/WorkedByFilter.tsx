/* Narrows the papers table to one person's work.
 *
 * Labelled "Worked on by" rather than "Filter by" because the column it acts on
 * has a specific meaning -- touched, not owned -- and a bare "Filter by" does
 * not say what it filters on.
 *
 * "Me" is a distinct value from the signed-in user's id, so a bookmarked link
 * keeps meaning "mine" for whoever opens it rather than pinning to one account.
 */
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { initialsFor } from '@/components/UserAvatar'
import { API_BASE_URL } from '@/lib/api'
import type { UserSummaryResp } from '@/api/generated/types.gen'
import type { IndexSearch } from '@/routeTree'

type Value = NonNullable<IndexSearch['worked_by']>

export function WorkedByFilter({
  value,
  people,
  onChange,
}: {
  value: Value
  people: UserSummaryResp[]
  onChange: (next: Value) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground whitespace-nowrap">
        Worked on by
      </label>
      <Select
        value={String(value)}
        onValueChange={(next: string | null) => {
          // Base UI's Select can emit null when a selection is cleared; nothing
          // here clears it, but "anyone" is the right reading if it ever does.
          if (next === null || next === 'anyone') return onChange('anyone')
          onChange(next === 'me' ? 'me' : Number(next))
        }}
      >
        <SelectTrigger className="w-52">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="anyone">Anyone</SelectItem>
          <SelectItem value="me">Me</SelectItem>
          {people.map((person) => (
            <SelectItem key={person.id} value={String(person.id)}>
              <span className="flex items-center gap-2">
                <Avatar size="sm">
                  <AvatarImage
                    src={person.avatar_url ? `${API_BASE_URL}${person.avatar_url}` : undefined}
                    alt={person.name}
                  />
                  <AvatarFallback>{initialsFor(person)}</AvatarFallback>
                </Avatar>
                {person.name}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
