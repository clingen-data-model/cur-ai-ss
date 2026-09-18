/* Small "at a glance" demographic snippet for the Occurrences table's
 * Patient column hover card -- age/sex/origin/phenotypes, in the spirit of
 * the pptx curation export's proband summary (lib/misc/curation/summary.py). */
import { useQuery } from '@tanstack/react-query'
import { getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet } from '@/api/generated'
import type { PatientResp } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'

const STALE_TIME = 5 * 60 * 1000
const MAX_PHENOTYPES_SHOWN = 6

function formatAge(value: number | null | undefined, unit: string | null | undefined): string | null {
  if (value == null || !unit) return null
  return `${value} ${unit.toLowerCase()}`
}

export function PatientHoverCardContent({ paperId, patient }: { paperId: number; patient: PatientResp }) {
  // Not embedded in PatientResp -- fetched only once the hover card actually
  // mounts this content (the preview card portal is closed-unmounted), so
  // hovering over a big occurrences table doesn't fire one request per row.
  const phenotypesQuery = useQuery({
    queryKey: ['phenotypes', paperId, patient.id],
    queryFn: () =>
      getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet({
        path: { paper_id: paperId, patient_id: patient.id },
      }),
    staleTime: STALE_TIME,
  })
  // Negated phenotypes ("does NOT have X") would be misleading in a
  // one-line snippet, so only affirmed/uncertain concepts are shown here --
  // the full picture with negation is still one click away in the detail panel.
  const phenotypeConcepts = (phenotypesQuery.data ?? [])
    .filter((p) => !p.negated)
    .map((p) => (p.uncertain ? `${p.concept}?` : p.concept))
  const shownPhenotypes = phenotypeConcepts.slice(0, MAX_PHENOTYPES_SHOWN)
  const extraPhenotypeCount = phenotypeConcepts.length - shownPhenotypes.length

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

      {phenotypesQuery.isPending ? (
        <p className="text-xs text-muted-foreground pt-1 border-t">Loading phenotypes…</p>
      ) : (
        shownPhenotypes.length > 0 && (
          <div className="pt-1 border-t space-y-0.5">
            <p className="text-xs text-muted-foreground">Phenotypes</p>
            <p className="text-xs">
              {shownPhenotypes.join(', ')}
              {extraPhenotypeCount > 0 ? ` +${extraPhenotypeCount} more` : ''}
            </p>
          </div>
        )
      )}
    </div>
  )
}
