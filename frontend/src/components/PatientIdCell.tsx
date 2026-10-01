import type { PatientResp } from '@/api/generated/types.gen'
import { EntityLink } from '@/components/EntityLink'
import { PatientHoverCardContent } from '@/components/PatientHoverCard'
import { PedigreeSymbol } from '@/components/PedigreeSymbol'

/** How a patient is named in every table: the pedigree symbol (sex and
 * affected status, with an asterisk for the proband) then the identifier.
 * Clicking the identifier runs onClick (open the row); hovering previews the
 * patient. */
export function PatientIdCell({
  paperId,
  patient,
  onClick,
}: {
  paperId: number
  patient: PatientResp
  onClick: () => void
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
    </div>
  )
}
