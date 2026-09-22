/* Search-as-you-type HPO term picker, backed by the server-side fuzzy match
 * at GET /hpo/search rather than a client-side filtered list -- the ontology
 * has tens of thousands of terms, too many to ship to the browser. Shared by
 * AddPhenotypeDialog (optional term at creation) and RelinkHpoDialog
 * (changing an existing link), so both stay in sync with one search/debounce
 * implementation. */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchHpoTermsHpoSearchGet } from '@/api/generated'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '@/components/ui/combobox'

const DEBOUNCE_MS = 250
const MIN_QUERY_LENGTH = 2

export function HpoCombobox({
  value,
  initialLabel,
  onValueChange,
  autoFocus,
}: {
  value: string | null
  initialLabel?: string | null
  onValueChange: (id: string | null, name: string | null) => void
  autoFocus?: boolean
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const [selectedLabel, setSelectedLabel] = useState<string | null>(initialLabel ?? null)
  const [debouncedQuery, setDebouncedQuery] = useState('')

  useEffect(() => {
    const query = (draft ?? '').trim()
    const handle = setTimeout(() => setDebouncedQuery(query), DEBOUNCE_MS)
    return () => clearTimeout(handle)
  }, [draft])

  const searchQuery = useQuery({
    queryKey: ['hpo-search', debouncedQuery],
    queryFn: () => searchHpoTermsHpoSearchGet({ query: { text: debouncedQuery } }),
    enabled: debouncedQuery.length >= MIN_QUERY_LENGTH,
  })
  const candidates = searchQuery.data ?? []

  const labelFor = (id: string | null): string => {
    if (id == null) return ''
    if (id === value && selectedLabel) return selectedLabel
    return candidates.find((c) => c.id === id)?.name ?? id
  }
  const inputValue = draft ?? labelFor(value)

  return (
    <Combobox
      value={value}
      itemToStringLabel={labelFor}
      inputValue={inputValue}
      onValueChange={(next: string | null) => {
        const candidate = candidates.find((c) => c.id === next)
        setSelectedLabel(candidate?.name ?? null)
        setDraft(null)
        onValueChange(next, candidate?.name ?? null)
      }}
      onInputValueChange={(next: string | null) => setDraft(next ?? '')}
    >
      <ComboboxInput placeholder="Search HPO terms..." showClear autoFocus={autoFocus} />
      <ComboboxContent>
        <ComboboxList>
          {candidates.map((c) => (
            <ComboboxItem key={c.id} value={c.id}>
              <span>{c.name}</span>
              <span className="text-muted-foreground text-xs">{c.id}</span>
            </ComboboxItem>
          ))}
          <ComboboxEmpty>
            {debouncedQuery.length < MIN_QUERY_LENGTH
              ? 'Type at least 2 characters to search'
              : 'No matching HPO terms.'}
          </ComboboxEmpty>
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
