/* A pipeline step's name for curators. The backend owns it (TaskType.label,
 * served by GET /task-types beside each step's description), so the timeline,
 * the Rerun dialog, flags, toasts and the paper chat all say "Finding
 * variants" for Variant Extraction. TaskType values stay the step's name in
 * requests.
 *
 * Synchronous on purpose: labels are read in plain functions (flag sources,
 * busy messages, toasts) as well as in components. The root layout's AuthGate
 * holds the first paint until GET /task-types has answered and registers the
 * labels here, so every caller sees them. */
import type { TaskType, TaskTypeResp } from '@/api/generated/types.gen'

const labels = new Map<string, string>()

export function registerTaskLabels(rows: Pick<TaskTypeResp, 'type' | 'label'>[]): void {
  for (const row of rows) labels.set(row.type, row.label)
}

export function taskLabel(type: TaskType | string): string {
  // Before the labels load (or for a type this build does not know), the
  // value itself, with "Patient" read as curators say it.
  return labels.get(type) ?? type.replace(/\bPatient\b/g, 'Individual')
}
