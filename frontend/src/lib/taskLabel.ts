/* The word curators see for a patient is "Individual" (since 2026-11-06),
 * while the API, the task types and the code keep "patient". TaskType values
 * are display strings that name the agents ('Individual Extraction'), so every
 * place one is shown goes through here. Requests still send the value. */
import type { TaskType } from '@/api/generated/types.gen'

export function taskLabel(type: TaskType | string): string {
  return type.replace(/\bPatient\b/g, 'Individual')
}
