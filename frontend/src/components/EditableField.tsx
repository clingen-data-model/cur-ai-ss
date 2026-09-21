/* Generic "label: editable value [evidence]" rows shared by the Patient,
 * Variant and Occurrence detail panels. Every edit goes through
 * usePendingEdit + HumanEditNoteDialog: a changed value doesn't save until
 * the curator explains why in the forced note dialog.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Check } from 'lucide-react'
import { EvidencePopover, type EvidenceLike } from '@/components/EvidencePopover'
import { HumanEditNoteDialog } from '@/components/HumanEditNoteDialog'
import { usePendingEdit } from '@/hooks/usePendingEdit'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandGroup, CommandItem, CommandList } from '@/components/ui/command'
import { pillColorFor } from '@/lib/pillColors'

const NONE_VALUE = '__none__'

function FieldRow({
  label,
  evidence,
  children,
}: {
  label: string
  evidence?: EvidenceLike | null
  children: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 border-b last:border-0">
      <span className="text-sm text-muted-foreground shrink-0 w-44">{label}</span>
      <div className="flex items-center gap-1 flex-1 justify-end min-w-0">
        {children}
        <EvidencePopover block={evidence} />
      </div>
    </div>
  )
}

export function EditableSelectRow({
  label,
  value,
  options,
  allowNone,
  evidence,
  onSave,
  isSaving,
}: {
  label: string
  value: string | null
  options: string[]
  allowNone?: boolean
  evidence?: EvidenceLike | null
  onSave: (value: string | null, note: string) => void
  isSaving?: boolean
}) {
  const pending = usePendingEdit<string | null>(onSave)
  return (
    <FieldRow label={label} evidence={evidence}>
      <Select value={value ?? NONE_VALUE} onValueChange={(v) => pending.propose(v === NONE_VALUE ? null : v)}>
        {/* Fixed width -- w-fit (the SelectTrigger default) sizes to
         * whichever option is currently selected, so every row in this panel
         * would resize independently as values change. A shared fixed width
         * keeps the whole column visually aligned instead. */}
        <SelectTrigger size="sm" className="h-7 text-xs w-60">
          {value === null ? '—' : <SelectValue />}
        </SelectTrigger>
        <SelectContent>
          {allowNone && <SelectItem value={NONE_VALUE}>—</SelectItem>}
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => {
          if (!open) pending.cancel()
        }}
        fieldLabel={label}
        defaultNote={evidence?.human_edit_note}
        isPending={isSaving}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={value ?? '—'}
        afterValue={pending.pendingValue ?? '—'}
      />
    </FieldRow>
  )
}

export function EditableSwitchRow({
  label,
  value,
  evidence,
  onSave,
  isSaving,
}: {
  label: string
  value: boolean
  evidence?: EvidenceLike | null
  onSave: (value: boolean, note: string) => void
  isSaving?: boolean
}) {
  const pending = usePendingEdit<boolean>(onSave)
  return (
    <FieldRow label={label} evidence={evidence}>
      <Switch checked={value} onCheckedChange={(v) => pending.propose(v)} />
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => {
          if (!open) pending.cancel()
        }}
        fieldLabel={label}
        defaultNote={evidence?.human_edit_note}
        isPending={isSaving}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={value ? 'Yes' : 'No'}
        afterValue={pending.pendingValue ? 'Yes' : 'No'}
      />
    </FieldRow>
  )
}

export function EditableTextRow({
  label,
  value,
  evidence,
  onSave,
  isSaving,
  disabled,
}: {
  label: string
  value: string
  evidence?: EvidenceLike | null
  onSave: (value: string, note: string) => void
  isSaving?: boolean
  disabled?: boolean
}) {
  const [draft, setDraft] = useState(value)
  const pending = usePendingEdit<string>(onSave)

  const commit = () => {
    if (draft !== value) pending.propose(draft)
    else setDraft(value)
  }

  return (
    <FieldRow label={label} evidence={evidence}>
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
        }}
        disabled={disabled}
        className="h-7 text-xs"
      />
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => {
          if (!open) {
            pending.cancel()
            setDraft(value)
          }
        }}
        fieldLabel={label}
        defaultNote={evidence?.human_edit_note}
        isPending={isSaving}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={value}
        afterValue={pending.pendingValue ?? ''}
      />
    </FieldRow>
  )
}

/** A numeric value with a separate unit selector. Only the value requires a
 * curator note (matches lib/ui/paper/patients.py: changing the unit alone
 * saves immediately, since there's no `<field>_unit_human_edit_note`). */
export function EditableAgeRow({
  label,
  value,
  unit,
  unitOptions,
  evidence,
  onSaveValue,
  onSaveUnit,
  isSaving,
}: {
  label: string
  value: number | null
  unit: string | null
  unitOptions: string[]
  evidence?: EvidenceLike | null
  onSaveValue: (value: number | null, note: string) => void
  onSaveUnit: (unit: string | null) => void
  isSaving?: boolean
}) {
  const [draft, setDraft] = useState(value != null ? String(value) : '')
  const pending = usePendingEdit<number | null>(onSaveValue)

  const commit = () => {
    const trimmed = draft.trim()
    const parsed = trimmed === '' ? null : Number(trimmed)
    if (parsed !== null && Number.isNaN(parsed)) {
      setDraft(value != null ? String(value) : '')
      return
    }
    if (parsed !== value) pending.propose(parsed)
    else setDraft(value != null ? String(value) : '')
  }

  return (
    <FieldRow label={label} evidence={evidence}>
      <Input
        type="number"
        min={0}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
        }}
        className="h-7 text-xs w-16"
      />
      <Select value={unit ?? NONE_VALUE} onValueChange={(v) => onSaveUnit(v === NONE_VALUE ? null : v)}>
        <SelectTrigger size="sm" className="h-7 text-xs w-24">
          {unit === null ? '—' : <SelectValue />}
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE_VALUE}>—</SelectItem>
          {unitOptions.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <HumanEditNoteDialog
        open={pending.isOpen}
        onOpenChange={(open) => {
          if (!open) {
            pending.cancel()
            setDraft(value != null ? String(value) : '')
          }
        }}
        fieldLabel={label}
        defaultNote={evidence?.human_edit_note}
        isPending={isSaving}
        onConfirm={(note) => pending.confirm(note)}
        beforeValue={value != null ? String(value) : '—'}
        afterValue={pending.pendingValue != null ? String(pending.pendingValue) : '—'}
      />
    </FieldRow>
  )
}

/** Text field that saves directly on blur, with no human-edit-note dialog --
 * for fields with no note capability on the backend (e.g. harmonized variant
 * fields, which carry one shared reasoning block and no per-field note). */
export function SimpleTextRow({
  label,
  value,
  evidence,
  onSave,
  caption,
}: {
  label: string
  value: string
  evidence?: EvidenceLike | null
  onSave: (value: string) => void
  caption?: ReactNode
}) {
  const [draft, setDraft] = useState(value)
  return (
    <FieldRow label={label} evidence={evidence}>
      <div className="flex flex-col items-end gap-0.5">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            if (draft !== value) onSave(draft)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur()
          }}
          className="h-7 text-xs"
        />
        {caption}
      </div>
    </FieldRow>
  )
}

/** A capped multi-select with no note dialog -- for fields with no note
 * capability on the backend (e.g. Paper Types, which has no evidence column
 * or `*_human_edit_note` field, matching Streamlit's plain `st.pills`). Saves
 * on close if the selection changed. */
export function SimpleMultiSelectRow({
  label,
  value,
  options,
  max,
  onSave,
}: {
  label: string
  value: string[]
  options: string[]
  max: number
  onSave: (value: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<string[]>(value)

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setDraft(value)
    } else {
      const changed = draft.length !== value.length || draft.some((v) => !value.includes(v))
      if (changed) onSave(draft)
    }
    setOpen(next)
  }

  const toggle = (option: string) => {
    setDraft((prev) => {
      if (prev.includes(option)) return prev.filter((o) => o !== option)
      if (prev.length >= max) return prev
      return [...prev, option]
    })
  }

  const atLimit = draft.length >= max

  return (
    <FieldRow label={label}>
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger className="flex flex-wrap justify-end gap-1 max-w-56 rounded p-0.5 hover:bg-muted cursor-pointer">
          {value.length === 0 ? (
            <span className="text-xs text-muted-foreground">Select...</span>
          ) : (
            value.map((v) => (
              <Badge key={v} className={pillColorFor(v)} variant="outline">
                {v}
              </Badge>
            ))
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="end">
          <Command>
            <p className="px-2 pt-2 text-xs text-muted-foreground">
              {atLimit ? `Maximum of ${max} selected` : `Select up to ${max}`}
            </p>
            <CommandList>
              <CommandGroup>
                {options.map((option) => {
                  const selected = draft.includes(option)
                  return (
                    <CommandItem
                      key={option}
                      value={option}
                      disabled={atLimit && !selected}
                      onSelect={() => toggle(option)}
                    >
                      {option}
                      {selected && <Check className="ml-auto size-4" />}
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </FieldRow>
  )
}

export function ReadOnlyRow({
  label,
  value,
  evidence,
}: {
  label: string
  value: ReactNode
  evidence?: EvidenceLike | null
}) {
  return (
    <FieldRow label={label} evidence={evidence}>
      <span className="text-sm text-right truncate max-w-64">{value}</span>
    </FieldRow>
  )
}
