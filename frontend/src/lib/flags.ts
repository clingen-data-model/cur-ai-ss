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
