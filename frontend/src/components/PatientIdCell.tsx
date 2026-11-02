import type { PatientResp } from '@/api/generated/types.gen'
import { EntityLink } from '@/components/EntityLink'
import { PatientHoverCardContent } from '@/components/PatientHoverCard'
import { PedigreeSymbol } from '@/components/PedigreeSymbol'

/** How a patient is named in every table: the pedigree symbol (sex and
 * affected status, with an asterisk for the proband) then the identifier.
 * The family is not part of the identifier (two families may each have a
 * II-1), so when showFamily is set it is printed beside the name. Clicking
 * the identifier runs onClick (open the row); hovering previews the patient. */
export function PatientIdCell({
  paperId,
  patient,
  onClick,
  showFamily = false,
}: {
  paperId: number
  patient: PatientResp
  onClick: () => void
  showFamily?: boolean
}) {
  return (
    <div className="flex items-center gap-1.5">
      <PedigreeSymbol patient={patient} />
      <EntityLink
        onClick={onClick}
        hoverContent={<PatientHoverCardContent paperId={paperId} patient={patient} />}
      >
        {patient.identifier}
      </EntityLink>
      {showFamily && (
        <span className="text-xs text-muted-foreground truncate">{patient.family_identifier}</span>
      )}
    </div>
  )
}

/** Whether a paper's patients span more than one family, in which case the
 * tables print the family beside each identifier. */
export function hasSeveralFamilies(patients: Pick<PatientResp, 'family_id'>[]): boolean {
  return new Set(patients.map((p) => p.family_id)).size > 1
}
