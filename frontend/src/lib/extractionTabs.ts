/** The tabs on a paper's extraction page, in display order. The page
 * reads the open one from the `tab` search param so a link can land on a
 * specific tab (the papers table's Patients / Variants / Flags counts). */
export const EXTRACTION_TABS = [
  'occurrences',
  'families',
  'unassociated-patients',
  'unassociated-variants',
  'flags',
  'pedigree',
  'paper-metadata',
] as const

export type ExtractionTab = (typeof EXTRACTION_TABS)[number]

export const DEFAULT_EXTRACTION_TAB: ExtractionTab = 'occurrences'

export function isExtractionTab(value: unknown): value is ExtractionTab {
  return typeof value === 'string' && (EXTRACTION_TABS as readonly string[]).includes(value)
}
