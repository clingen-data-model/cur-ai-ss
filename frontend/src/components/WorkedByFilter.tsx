/* Narrows the papers table to one person's work.
 *
 * Labelled "Worked on by" rather than "Filter by" because the column it acts on
 * has a specific meaning -- touched, not owned -- and a bare "Filter by" does
 * not say what it filters on.
 *
 * "Me" is a distinct value from the signed-in user's id, so a bookmarked link
 * keeps meaning "mine" for whoever opens it rather than pinning to one account.
 *
 * A combobox rather than a select so the list stays usable as the team grows;
 * with nine people scrolling is fine, but typing a name is faster and the
 * control should not need replacing later.
 */
import { useMemo, useState } from 'react'
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
import type { UserSummaryResp } from '@/api/generated/types.gen'
import type { IndexSearch } from '@/routeTree'

type Value = NonNullable<IndexSearch['worked_by']>

interface Option {
  /** Stringified because the combobox compares values by identity. */
  value: string
  label: string
  person?: UserSummaryResp
}

export function WorkedByFilter({
  value,
  people,
  onChange,
}: {
  value: Value
  people: UserSummaryResp[]
  onChange: (next: Value) => void
}) {
  // null means "not typing" -- the input then shows the selected option's label.
  // A plain string default cannot work: the label is only knowable once `people`
  // has loaded, and Base UI derives its own initial input text once on mount
  // (useRefWithInit in AriaCombobox), so a bookmarked ?worked_by=7 would render
  // blank forever. Controlling the value lets it correct itself when they arrive.
  const [draft, setDraft] = useState<string | null>(null)

  const options = useMemo<Option[]>(
    () => [
      { value: 'anyone', label: 'Anyone' },
      { value: 'me', label: 'Me' },
      ...people.map((person) => ({
        value: String(person.id),
        label: person.name,
        person,
      })),
    ],
    [people],
  )

  const labelFor = (v: string) => options.find((o) => o.value === v)?.label ?? ''
  const inputValue = draft ?? labelFor(String(value))

  // Filtered here rather than by the primitive so what the list shows and what
  // ComboboxEmpty reacts to are the same array. Only a draft filters: showing
  // the full list when a selection is displayed keeps the menu from opening
  // pre-filtered to the one option already chosen.
  const visible = useMemo(() => {
    const q = (draft ?? '').trim().toLowerCase()
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options
  }, [options, draft])

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground whitespace-nowrap">
        Worked on by
      </label>
      <Combobox
        value={String(value)}
        // Without this the input renders the raw value, which for a person is
        // their numeric id -- the selected filter read "7" instead of a name.
        itemToStringLabel={labelFor}
        inputValue={inputValue}
        onValueChange={(next: string | null) => {
          setDraft(null) // back to showing the selection rather than the query
          if (next === null || next === 'anyone') return onChange('anyone')
          onChange(next === 'me' ? 'me' : Number(next))
        }}
        onInputValueChange={(next: string | null) => setDraft(next ?? '')}
      >
        <ComboboxInput placeholder="Anyone" className="w-52" showClear />
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
