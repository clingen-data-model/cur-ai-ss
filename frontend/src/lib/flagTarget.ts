import type { FlagResp } from '@/api/generated/types.gen'

/** Which of an occurrence row's two detail panels a chip opens. */
export type OccurrenceView = 'patient' | 'variant'

/** Where a flag's About chip takes the reader: the row it is about, on the
 * tab that shows it. A phenotype opens its patient, since phenotypes live
 * in the patient's detail panel. */
export type FlagTarget =
  | { kind: 'family'; id: number }
  | { kind: 'patient'; id: number }
  | { kind: 'variant'; id: number }
  | { kind: 'occurrence'; id: number; view?: OccurrenceView }

/** The rows a flag links, in the order the About column shows them. */
export function flagTargets(flag: FlagResp): FlagTarget[] {
  const targets: FlagTarget[] = []
  if (flag.family_id != null) targets.push({ kind: 'family', id: flag.family_id })
  if (flag.occurrence_id != null) targets.push({ kind: 'occurrence', id: flag.occurrence_id })
  else {
    if (flag.patient_id != null) targets.push({ kind: 'patient', id: flag.patient_id })
    if (flag.variant_id != null) targets.push({ kind: 'variant', id: flag.variant_id })
  }
  if (flag.paired_occurrence_id != null) targets.push({ kind: 'occurrence', id: flag.paired_occurrence_id })
  return targets
}
