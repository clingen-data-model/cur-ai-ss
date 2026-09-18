/* The occurrence-level fields editable directly from the Occurrences table:
 * Zygosity, Inheritance, De Novo and Testing Methods. Disease Name stays
 * read-only -- PatientVariantOccurrenceUpdateRequest has no field for it,
 * matching the Streamlit grid (which never makes it editable either).
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check } from 'lucide-react'
import { updateOccurrencePapersPaperIdOccurrencesOccurrenceIdPatch } from '@/api/generated'
import { Inheritance, TestingMethod, Zygosity } from '@/api/generated/types.gen'
import type { PatientVariantOccurrenceResp, PatientVariantOccurrenceUpdateRequest } from '@/api/generated/types.gen'
import { EvidencePopover } from '@/components/EvidencePopover'
import { HumanEditNoteDialog } from '@/components/HumanEditNoteDialog'
import { usePendingEdit } from '@/hooks/usePendingEdit'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandGroup, CommandItem, CommandList } from '@/components/ui/command'
import { pillColorFor } from '@/lib/pillColors'
import { apiErrorMessage } from '@/lib/apiError'

/** PatientVariantOccurrenceUpdateRequest.max_two_methods rejects a third
 * selection server-side -- enforced here too so a curator sees it at
 * selection time instead of a generic save failure after the fact. */
const MAX_TESTING_METHODS = 2

function useOccurrenceMutation(paperId: number, occurrenceId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: PatientVariantOccurrenceUpdateRequest) =>
      updateOccurrencePapersPaperIdOccurrencesOccurrenceIdPatch({
        path: { paper_id: paperId, occurrence_id: occurrenceId },
        body,
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['occurrences', paperId] })
      // update_occurrence calls _touch_paper server-side, which backs the
      // papers table's touched_by filter -- without this, "worked on by"
      // stays stale until the 5-minute staleTime lapses on its own.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to save occurrence')),
  })
}

export function EditableZygosityCell({
  paperId,
  occurrence,
}: {
  paperId: number
  occurrence: PatientVariantOccurrenceResp
}) {
  const mutation = useOccurrenceMutation(paperId, occurrence.id)
  const pending = usePendingEdit<string>((value, note) =>
    mutation.mutate({ zygosity: value as Zygosity, zygosity_human_edit_note: note }),
  )
  return (
    <div className="flex items-center gap-1">
      <Select value={occurrence.zygosity} onValueChange={(v) => v && pending.propose(v)}>
        <SelectTrigger size="sm" className="h-7 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.values(Zygosity).map((z) => (
            <SelectItem key={z} value={z}>
              {z}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <EvidencePopover block={occurrence.zygosity_evidence} />
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => !open && pending.cancel()}
        fieldLabel="Zygosity"
        defaultNote={occurrence.zygosity_evidence.human_edit_note}
        isPending={mutation.isPending}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={occurrence.zygosity}
        afterValue={pending.pendingValue ?? occurrence.zygosity}
      />
    </div>
  )
}

export function EditableInheritanceCell({
  paperId,
  occurrence,
}: {
  paperId: number
  occurrence: PatientVariantOccurrenceResp
}) {
  const mutation = useOccurrenceMutation(paperId, occurrence.id)
  const pending = usePendingEdit<string>((value, note) =>
    mutation.mutate({ inheritance: value as Inheritance, inheritance_human_edit_note: note }),
  )
  return (
    <div className="flex items-center gap-1">
      <Select value={occurrence.inheritance} onValueChange={(v) => v && pending.propose(v)}>
        <SelectTrigger size="sm" className="h-7 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.values(Inheritance).map((i) => (
            <SelectItem key={i} value={i}>
              {i}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <EvidencePopover block={occurrence.inheritance_evidence} />
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => !open && pending.cancel()}
        fieldLabel="Inheritance"
        defaultNote={occurrence.inheritance_evidence.human_edit_note}
        isPending={mutation.isPending}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={occurrence.inheritance}
        afterValue={pending.pendingValue ?? occurrence.inheritance}
      />
    </div>
  )
}

export function EditableDeNovoCell({
  paperId,
  occurrence,
}: {
  paperId: number
  occurrence: PatientVariantOccurrenceResp
}) {
  const mutation = useOccurrenceMutation(paperId, occurrence.id)
  const pending = usePendingEdit<boolean>((value, note) =>
    mutation.mutate({ de_novo: value, de_novo_human_edit_note: note }),
  )
  return (
    <div className="flex items-center gap-1">
      <Switch checked={occurrence.de_novo} onCheckedChange={(v) => pending.propose(v)} />
      <EvidencePopover block={occurrence.de_novo_evidence} />
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => !open && pending.cancel()}
        fieldLabel="De Novo"
        defaultNote={occurrence.de_novo_evidence.human_edit_note}
        isPending={mutation.isPending}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={occurrence.de_novo ? 'Yes' : 'No'}
        afterValue={pending.pendingValue ? 'Yes' : 'No'}
      />
    </div>
  )
}

export function EditableTestingMethodsCell({
  paperId,
  occurrence,
}: {
  paperId: number
  occurrence: PatientVariantOccurrenceResp
}) {
  const mutation = useOccurrenceMutation(paperId, occurrence.id)
  const pending = usePendingEdit<string[]>((methods, note) =>
    mutation.mutate({ testing_methods: methods as TestingMethod[], testing_methods_note: note }),
  )
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<string[]>(occurrence.testing_methods)

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setDraft(occurrence.testing_methods)
    } else {
      const before = occurrence.testing_methods
      const changed =
        draft.length !== before.length || draft.some((m) => !before.includes(m as never))
      if (changed) pending.propose(draft)
    }
    setOpen(next)
  }

  const toggle = (method: string) => {
    setDraft((prev) => {
      if (prev.includes(method)) return prev.filter((m) => m !== method)
      if (prev.length >= MAX_TESTING_METHODS) return prev
      return [...prev, method]
    })
  }

  const atLimit = draft.length >= MAX_TESTING_METHODS

  return (
    <div className="flex items-center gap-1">
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger className="flex flex-wrap gap-1 max-w-56 rounded p-0.5 hover:bg-muted cursor-pointer">
          {occurrence.testing_methods.length === 0 ? (
            <span className="text-xs text-muted-foreground">Select...</span>
          ) : (
            occurrence.testing_methods.map((method) => (
              <Badge key={method} className={pillColorFor(method)} variant="outline">
                {method}
              </Badge>
            ))
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <Command>
            <p className="px-2 pt-2 text-xs text-muted-foreground">
              {atLimit ? 'Maximum of 2 selected' : 'Select up to 2'}
            </p>
            <CommandList>
              <CommandGroup>
                {Object.values(TestingMethod).map((method) => {
                  const selected = draft.includes(method)
                  return (
                    <CommandItem
                      key={method}
                      value={method}
                      disabled={atLimit && !selected}
                      onSelect={() => toggle(method)}
                    >
                      {method}
                      {selected && <Check className="ml-auto size-4" />}
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      <EvidencePopover
        block={
          occurrence.testing_methods_evidence[0]
            ? { ...occurrence.testing_methods_evidence[0], human_edit_note: occurrence.testing_methods_note }
            : occurrence.testing_methods_note
              ? { reasoning: '', human_edit_note: occurrence.testing_methods_note }
              : null
        }
      />
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => !open && pending.cancel()}
        fieldLabel="Testing Methods"
        defaultNote={occurrence.testing_methods_note}
        isPending={mutation.isPending}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={occurrence.testing_methods.join(', ') || '—'}
        afterValue={(pending.pendingValue ?? []).join(', ') || '—'}
      />
    </div>
  )
}
