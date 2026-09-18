/* Small "at a glance" demographic snippet for the Occurrences table's
 * Patient column hover card -- age/sex/origin, in the spirit of the pptx
 * curation export's proband summary (lib/misc/curation/summary.py). */
import type { PatientResp } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'

function formatAge(value: number | null | undefined, unit: string | null | undefined): string | null {
  if (value == null || !unit) return null
  return `${value} ${unit.toLowerCase()}`
}

export function PatientHoverCardContent({ patient }: { patient: PatientResp }) {
  const age =
    formatAge(patient.age_report, patient.age_report_unit) ??
    formatAge(patient.age_diagnosis, patient.age_diagnosis_unit)
  const ageAtDeath = formatAge(patient.age_death, patient.age_death_unit)
  const country = patient.country_of_origin !== 'Unknown' ? patient.country_of_origin : null
  const race = patient.race !== 'Unknown' ? patient.race : null
  const ethnicity = patient.ethnicity !== 'Unknown' ? patient.ethnicity : null

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold truncate">{patient.identifier}</p>
        <Badge variant="outline" className="text-[10px] shrink-0">
          {patient.proband_status}
        </Badge>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs">
        <dt className="text-muted-foreground">Sex</dt>
        <dd className="text-right truncate">{patient.sex}</dd>
        {age && (
          <>
            <dt className="text-muted-foreground">Age</dt>
            <dd className="text-right truncate">{age}</dd>
          </>
        )}
        {ageAtDeath && (
          <>
            <dt className="text-muted-foreground">Age at Death</dt>
            <dd className="text-right truncate">{ageAtDeath}</dd>
          </>
        )}
        {country && (
          <>
            <dt className="text-muted-foreground">Country</dt>
            <dd className="text-right truncate">{country}</dd>
          </>
        )}
        {race && (
          <>
            <dt className="text-muted-foreground">Race</dt>
            <dd className="text-right truncate">{race}</dd>
          </>
        )}
        {ethnicity && (
          <>
            <dt className="text-muted-foreground">Ethnicity</dt>
            <dd className="text-right truncate">{ethnicity}</dd>
          </>
        )}
      </dl>

      <p className="text-xs text-muted-foreground pt-1 border-t">
        {patient.affected_status}
        {patient.is_obligate_carrier ? ' · Obligate carrier' : ''}
      </p>
    </div>
  )
}
