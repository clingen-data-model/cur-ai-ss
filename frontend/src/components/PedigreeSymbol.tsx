import type { PatientResp } from '@/api/generated/types.gen'

/** The pedigree symbol for a person: square male, circle female, diamond for
 * anyone else; filled when affected, hollow when unaffected, dashed when
 * unknown; an asterisk when they are the proband. */
export function PedigreeSymbol({
  patient,
}: {
  patient: Pick<PatientResp, 'sex' | 'affected_status' | 'proband_status'>
}) {
  const affected = patient.affected_status === 'Affected'
  const unknown = patient.affected_status === 'Unknown'
  const stroke = 'currentColor'
  const fill = affected ? '#f43f5e' : 'none'
  const common = {
    fill,
    stroke,
    strokeWidth: 1.5,
    strokeDasharray: unknown ? '2 2' : undefined,
  }
  const shape =
    patient.sex === 'Male' ? (
      <rect x="3" y="3" width="14" height="14" {...common} />
    ) : patient.sex === 'Female' ? (
      <circle cx="10" cy="10" r="7" {...common} />
    ) : (
      <polygon points="10,2 18,10 10,18 2,10" {...common} />
    )
  const title = `${patient.sex}, ${patient.affected_status.toLowerCase()}${
    patient.proband_status === 'Proband' ? ', proband' : ''
  }`
  return (
    <span className="inline-flex items-center gap-0.5" title={title}>
      <svg width="20" height="20" viewBox="0 0 20 20" className="text-muted-foreground" aria-label={title}>
        {shape}
      </svg>
      {patient.proband_status === 'Proband' && <span className="text-xs text-muted-foreground">*</span>}
    </span>
  )
}
