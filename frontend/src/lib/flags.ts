import { TaskType } from '@/api/generated/types.gen'
import type { FlagResp } from '@/api/generated/types.gen'

/** The agent that raised a flag, as a reader would name it. `source` is the
 * TaskType member's *name* (PATIENT_EXTRACTION); the enum maps it to the
 * label the rest of the UI uses for that task. */
export function flagSourceLabel(flag: Pick<FlagResp, 'source'>): string {
  return (TaskType as Record<string, string>)[flag.source] ?? flag.source
}

/** Open flags first, then newest first within each group. */
export function sortFlags(flags: FlagResp[]): FlagResp[] {
  return [...flags].sort((a, b) => {
    const aOpen = a.resolved_at == null ? 0 : 1
    const bOpen = b.resolved_at == null ? 0 : 1
    return aOpen - bOpen || b.id - a.id
  })
}

/** What each closed flag kind means, for the badge and its tooltip. */
export const FLAG_KIND_LABELS: Record<string, { label: string; hint: string }> = {
  excluded: { label: 'Excluded', hint: 'Something the paper describes that a rule kept out of the output' },
  conflict: { label: 'Conflict', hint: 'Two places in the paper disagree about one value; one was chosen' },
  ambiguous: { label: 'Ambiguous', hint: 'Two readings of the paper both fit; one was chosen' },
  inferred: { label: 'Inferred', hint: 'A value taken from somewhere other than a statement about the thing itself' },
  unresolved: { label: 'Unresolved', hint: 'A lookup could not settle it; the output is partial or empty' },
  mismatch: { label: 'Mismatch', hint: 'The best available term or record does not fit what the paper says' },
  alternative_cause: {
    label: 'Alternative cause',
    hint: 'The paper reports another explanation of this person\'s phenotype, such as a finding in a different gene',
  },
}

export function flagKindLabel(flag: Pick<FlagResp, 'kind'>): string {
  return FLAG_KIND_LABELS[flag.kind]?.label ?? flag.kind
}
