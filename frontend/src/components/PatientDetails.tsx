import React, { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { SaveIcon, HighlighterIcon } from 'lucide-react'
import {
  updatePatientPapersPaperIdPatientsPatientIdPatch,
  AffectedStatus,
  AgeUnit,
  CountryCode,
  ProbandStatus,
  RaceEthnicity,
  RelationshipToProband,
  SexAtBirth,
  TwinType,
} from '@/api/generated'
import type { PatientResp } from '@/api/generated/types.gen'

// The generator expands EvidenceBlock[T] into a separate type per T (HumanEvidenceBlockStr,
// HumanEvidenceBlockProbandStatus, etc.). This generic reconstructs the original shape so
// components can accept any evidence block without importing every instantiation.
type HumanEvidenceBlock<T = string> = {
  value: T
  reasoning: string
  quote?: string | null
  table_id?: number | null
  image_id?: number | null
  is_supplement?: boolean
  human_edit_note?: string | null
}
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Combobox,
  ComboboxInput,
  ComboboxContent,
  ComboboxList,
  ComboboxItem,
  ComboboxEmpty,
} from '@/components/ui/combobox'

const PROBAND_STATUS_OPTIONS = Object.values(ProbandStatus)
const AFFECTED_STATUS_OPTIONS = Object.values(AffectedStatus)
const SEX_OPTIONS = Object.values(SexAtBirth)
const AGE_UNIT_OPTIONS: (AgeUnit | '')[] = ['', ...Object.values(AgeUnit)]
const RACE_ETHNICITY_OPTIONS = Object.values(RaceEthnicity)
const RELATIONSHIP_OPTIONS: (RelationshipToProband | '')[] = ['', ...Object.values(RelationshipToProband)]
const TWIN_TYPE_OPTIONS: (TwinType | '')[] = ['', ...Object.values(TwinType)]
const COUNTRY_CODES = Object.values(CountryCode)

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="col-span-2 mt-2 pb-1 border-b border-border">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {children}
      </h3>
    </div>
  )
}

export type HighlightArgs = { query: string; tableId?: number | null; imageId?: number | null }

function EvidenceCell({
  evidence,
  onHighlight,
}: {
  evidence: HumanEvidenceBlock<unknown>
  onHighlight?: (args: HighlightArgs) => void
}) {
  const { reasoning, quote } = evidence
  const query = quote || (evidence.value != null ? String(evidence.value) : null)
  return (
    <div className="pt-5 text-xs text-muted-foreground space-y-1">
      <div className="flex items-start justify-between gap-1">
        {reasoning ? <p className="italic leading-snug">{reasoning}</p> : <span />}
        {query && onHighlight && (
          <button
            type="button"
            onClick={() => onHighlight({ query, tableId: evidence.table_id, imageId: evidence.image_id })}
            title="Highlight in PDF"
            className="shrink-0 p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <HighlighterIcon className="size-3.5" />
          </button>
        )}
      </div>
      {quote ? <p className="text-muted-foreground/60 leading-snug">"{quote}"</p> : null}
      {!reasoning && !quote ? <p className="text-muted-foreground/30">—</p> : null}
    </div>
  )
}

function FieldRow({
  label,
  evidence,
  onHighlight,
  children,
}: {
  label: string
  evidence: HumanEvidenceBlock<unknown>
  onHighlight?: (args: HighlightArgs) => void
  children: React.ReactNode
}) {
  return (
    <>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground block">{label}</label>
        {children}
      </div>
      <EvidenceCell evidence={evidence} onHighlight={onHighlight} />
    </>
  )
}

function AgeRow({
  label,
  evidence,
  onHighlight,
  value,
  unit,
  onValueChange,
  onUnitChange,
}: {
  label: string
  evidence: HumanEvidenceBlock<unknown>
  onHighlight?: (args: HighlightArgs) => void
  value: number | null
  unit: AgeUnit | null | undefined
  onValueChange: (v: number | null) => void
  onUnitChange: (u: AgeUnit | null) => void
}) {
  return (
    <>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground block">{label}</label>
        <div className="flex gap-2">
          <Input
            type="number"
            min={0}
            className="w-20 h-8 text-sm"
            value={value ?? ''}
            onChange={(e) => {
              const v = e.target.value === '' ? null : Number(e.target.value)
              onValueChange(v)
            }}
          />
          <Select
            value={unit ?? ''}
            onValueChange={(v) => onUnitChange((v as AgeUnit) || null)}
          >
            <SelectTrigger className="w-24 h-8 text-sm">
              <SelectValue placeholder="Unit" />
            </SelectTrigger>
            <SelectContent>
              {AGE_UNIT_OPTIONS.map((u) => (
                <SelectItem key={u} value={u}>{u || '—'}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <EvidenceCell evidence={evidence} onHighlight={onHighlight} />
    </>
  )
}

type FormState = {
  identifier: string
  proband_status: ProbandStatus
  affected_status: AffectedStatus
  sex: SexAtBirth
  age_diagnosis: number | null
  age_diagnosis_unit: AgeUnit | null
  age_report: number | null
  age_report_unit: AgeUnit | null
  age_death: number | null
  age_death_unit: AgeUnit | null
  country_of_origin: CountryCode
  race_ethnicity: RaceEthnicity
  is_obligate_carrier: boolean | null
  relationship_to_proband: RelationshipToProband | null
  twin_type: TwinType | null
}

function patientToForm(patient: PatientResp): FormState {
  return {
    identifier: patient.identifier,
    proband_status: patient.proband_status,
    affected_status: patient.affected_status,
    sex: patient.sex,
    age_diagnosis: patient.age_diagnosis,
    age_diagnosis_unit: patient.age_diagnosis_unit ?? null,
    age_report: patient.age_report,
    age_report_unit: patient.age_report_unit ?? null,
    age_death: patient.age_death,
    age_death_unit: patient.age_death_unit ?? null,
    country_of_origin: patient.country_of_origin,
    race_ethnicity: patient.race_ethnicity,
    is_obligate_carrier: patient.is_obligate_carrier,
    relationship_to_proband: patient.relationship_to_proband,
    twin_type: patient.twin_type,
  }
}

function isDirty(form: FormState, patient: PatientResp): boolean {
  return (
    form.identifier !== patient.identifier ||
    form.proband_status !== patient.proband_status ||
    form.affected_status !== patient.affected_status ||
    form.sex !== patient.sex ||
    form.age_diagnosis !== patient.age_diagnosis ||
    form.age_diagnosis_unit !== (patient.age_diagnosis_unit ?? null) ||
    form.age_report !== patient.age_report ||
    form.age_report_unit !== (patient.age_report_unit ?? null) ||
    form.age_death !== patient.age_death ||
    form.age_death_unit !== (patient.age_death_unit ?? null) ||
    form.country_of_origin !== patient.country_of_origin ||
    form.race_ethnicity !== patient.race_ethnicity ||
    form.is_obligate_carrier !== patient.is_obligate_carrier ||
    form.relationship_to_proband !== patient.relationship_to_proband ||
    form.twin_type !== patient.twin_type
  )
}

interface PatientDetailsProps {
  patient: PatientResp
  paperId: number
  onHighlight?: (args: HighlightArgs) => void
}

export function PatientDetails({ patient, paperId, onHighlight }: PatientDetailsProps) {
  const [form, setForm] = useState<FormState>(() => patientToForm(patient))
  const queryClient = useQueryClient()

  useEffect(() => {
    setForm(patientToForm(patient))
  }, [patient.id])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const mutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      updatePatientPapersPaperIdPatientsPatientIdPatch({
        path: { paper_id: paperId, patient_id: patient.id },
        body: body as any,
      }),
    onSuccess: () => {
      toast.success('Patient saved')
      queryClient.invalidateQueries({ queryKey: ['patients', paperId] })
    },
    onError: (err: any) => {
      toast.error(`Save failed: ${err?.message ?? 'Unknown error'}`)
    },
  })

  const dirty = isDirty(form, patient)

  const handleSave = () => {
    // Re-normalize patient into FormState so null-coercions (e.g. age_unit ?? null)
    // are comparable, then send only the keys whose values actually changed.
    const baseline = patientToForm(patient)
    const changes = Object.fromEntries(
      (Object.keys(form) as (keyof FormState)[])
        .filter((k) => form[k] !== baseline[k])
        .map((k) => [k, form[k]])
    )
    mutation.mutate(changes)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
        <div>
          <p className="text-sm font-semibold">{patient.identifier}</p>
          <p className="text-xs text-muted-foreground">{patient.family_identifier}</p>
        </div>
        {dirty && (
          <Button
            size="sm"
            onClick={handleSave}
            disabled={mutation.isPending}
            className="gap-1.5"
          >
            <SaveIcon className="size-3.5" />
            Save
          </Button>
        )}
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-2 gap-x-4 px-4 pt-3 pb-1 shrink-0">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Field</p>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Reasoning</p>
      </div>

      {/* Scrollable fields */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">

          <SectionHeader>Core Info</SectionHeader>

          <FieldRow label="Patient Identifier" evidence={patient.identifier_evidence} onHighlight={onHighlight}>
            <Input className="h-8 text-sm" value={form.identifier} onChange={(e) => set('identifier', e.target.value)} />
          </FieldRow>

          <FieldRow label="Family Identifier" evidence={patient.family_assignment_evidence} onHighlight={onHighlight}>
            <Input className="h-8 text-sm" value={patient.family_identifier} disabled />
          </FieldRow>

          <SectionHeader>Status</SectionHeader>

          <FieldRow label="Proband Status" evidence={patient.proband_status_evidence} onHighlight={onHighlight}>
            <Select value={form.proband_status} onValueChange={(v) => set('proband_status', v as ProbandStatus)}>
              <SelectTrigger className="h-8 text-sm w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{PROBAND_STATUS_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
            </Select>
          </FieldRow>

          <FieldRow label="Affected Status" evidence={patient.affected_status_evidence} onHighlight={onHighlight}>
            <Select value={form.affected_status} onValueChange={(v) => set('affected_status', v as AffectedStatus)}>
              <SelectTrigger className="h-8 text-sm w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{AFFECTED_STATUS_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
            </Select>
          </FieldRow>

          <FieldRow label="Sex at Birth" evidence={patient.sex_evidence} onHighlight={onHighlight}>
            <Select value={form.sex} onValueChange={(v) => set('sex', v as SexAtBirth)}>
              <SelectTrigger className="h-8 text-sm w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{SEX_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
            </Select>
          </FieldRow>

          <SectionHeader>Ages</SectionHeader>

          <AgeRow label="Age at Diagnosis" evidence={patient.age_diagnosis_evidence} onHighlight={onHighlight}
            value={form.age_diagnosis} unit={form.age_diagnosis_unit}
            onValueChange={(v) => set('age_diagnosis', v)} onUnitChange={(u) => set('age_diagnosis_unit', u)} />

          <AgeRow label="Age at Report" evidence={patient.age_report_evidence} onHighlight={onHighlight}
            value={form.age_report} unit={form.age_report_unit}
            onValueChange={(v) => set('age_report', v)} onUnitChange={(u) => set('age_report_unit', u)} />

          <AgeRow label="Age at Death" evidence={patient.age_death_evidence} onHighlight={onHighlight}
            value={form.age_death} unit={form.age_death_unit}
            onValueChange={(v) => set('age_death', v)} onUnitChange={(u) => set('age_death_unit', u)} />

          <SectionHeader>Demographics</SectionHeader>

          <FieldRow label="Country of Origin" evidence={patient.country_of_origin_evidence} onHighlight={onHighlight}>
            <Combobox value={form.country_of_origin} onValueChange={(v) => set('country_of_origin', v as CountryCode)}>
              <ComboboxInput className="h-8 text-sm w-full" showTrigger showClear />
              <ComboboxContent>
                <ComboboxList>
                  <ComboboxEmpty>No country found.</ComboboxEmpty>
                  {COUNTRY_CODES.map((c) => <ComboboxItem key={c} value={c}>{c}</ComboboxItem>)}
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
          </FieldRow>

          <FieldRow label="Race / Ethnicity" evidence={patient.race_ethnicity_evidence} onHighlight={onHighlight}>
            <Select value={form.race_ethnicity} onValueChange={(v) => set('race_ethnicity', v as RaceEthnicity)}>
              <SelectTrigger className="h-8 text-sm w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{RACE_ETHNICITY_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
            </Select>
          </FieldRow>

          <SectionHeader>Segregation Analysis</SectionHeader>

          <FieldRow label="Is Obligate Carrier" evidence={patient.is_obligate_carrier_evidence ?? { value: '', reasoning: '' }} onHighlight={onHighlight}>
            <div className="flex items-center gap-2 h-8">
              <Switch checked={form.is_obligate_carrier ?? false} onCheckedChange={(c) => set('is_obligate_carrier', c)} />
              <span className="text-sm text-muted-foreground">
                {form.is_obligate_carrier == null ? 'Unknown' : form.is_obligate_carrier ? 'Yes' : 'No'}
              </span>
            </div>
          </FieldRow>

          <FieldRow label="Relationship to Proband" evidence={patient.relationship_to_proband_evidence ?? { value: '', reasoning: '' }} onHighlight={onHighlight}>
            <Select value={form.relationship_to_proband ?? ''} onValueChange={(v) => set('relationship_to_proband', (v as RelationshipToProband) || null)}>
              <SelectTrigger className="h-8 text-sm w-full"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{RELATIONSHIP_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o || '—'}</SelectItem>)}</SelectContent>
            </Select>
          </FieldRow>

          <FieldRow label="Twin Type" evidence={patient.twin_type_evidence ?? { value: '', reasoning: '' }} onHighlight={onHighlight}>
            <Select value={form.twin_type ?? ''} onValueChange={(v) => set('twin_type', (v as TwinType) || null)}>
              <SelectTrigger className="h-8 text-sm w-full"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{TWIN_TYPE_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o || '—'}</SelectItem>)}</SelectContent>
            </Select>
          </FieldRow>

        </div>
      </div>
    </div>
  )
}

