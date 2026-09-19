/* Narrows the papers table to one reviewer's assigned papers.
 *
 * Independent from the Review Status filter (a status bucket) rather than
 * folded into it, so the two compose -- e.g. "In progress" + "Assigned to
 * Jane" -- and so this list can hold every active account without making the
 * status dropdown scroll for it.
 *
 * A combobox rather than a plain <select>, same reasoning as WorkedByFilter:
 * a searchable list scales better than scrolling as the team grows.
 *
 * Sourced from every active account (useUsers), not paper collaborators like
 * "Worked on by" -- the point is to be able to filter for someone who has not
 * been assigned anything yet.
 */
import { useEffect, useMemo, useState } from 'react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '@/components/ui/combobox'
import { initialsFor } from '@/components/UserAvatar'
import { API_BASE_URL } from '@/lib/api'
import { useUsers } from '@/hooks/useUsers'
import type { UserSummaryResp } from '@/api/generated/types.gen'

const ANY = 'anyone'

interface Option {
  /** Stringified because the combobox compares values by identity. */
  value: string
  label: string
  person?: UserSummaryResp
}

export function ReviewAssigneeFilter({
  value,
  onChange,
}: {
  value: number | undefined
  onChange: (next: number | undefined) => void
}) {
  const { users } = useUsers()

  // null means "not typing" -- the input then shows the selected option's
  // label. See WorkedByFilter for why this can't just be a plain default.
  const [draft, setDraft] = useState<string | null>(null)

  useEffect(() => {
    setDraft(null)
  }, [value])

  const options = useMemo<Option[]>(
    () => [
      { value: ANY, label: 'Any' },
      ...users.map((user) => ({ value: String(user.id), label: user.name, person: user })),
    ],
    [users],
  )

  const labelFor = (v: string) => options.find((o) => o.value === v)?.label ?? ''
  const inputValue = draft ?? labelFor(value === undefined ? ANY : String(value))

  const visible = useMemo(() => {
    const q = (draft ?? '').trim().toLowerCase()
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options
  }, [options, draft])

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground whitespace-nowrap">Assigned to</label>
      <Combobox
        value={value === undefined ? ANY : String(value)}
        itemToStringLabel={labelFor}
        inputValue={inputValue}
        onValueChange={(next: string | null) => {
          setDraft(labelFor(next ?? ANY))
          onChange(next === null || next === ANY ? undefined : Number(next))
        }}
        onInputValueChange={(next: string | null) => setDraft(next ?? '')}
      >
        <ComboboxInput placeholder="Any" className="w-40" showClear />
        <ComboboxContent>
          <ComboboxList>
            {visible.map((option) => (
              <ComboboxItem key={option.value} value={option.value}>
                <span className="flex items-center gap-2">
                  {option.person && (
                    <Avatar size="sm">
                      <AvatarImage
                        src={
                          option.person.avatar_url
                            ? `${API_BASE_URL}${option.person.avatar_url}`
                            : undefined
                        }
                        alt={option.label}
                      />
                      <AvatarFallback>{initialsFor(option.person)}</AvatarFallback>
                    </Avatar>
                  )}
                  {option.label}
                </span>
              </ComboboxItem>
            ))}
            <ComboboxEmpty>No one by that name.</ComboboxEmpty>
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}
