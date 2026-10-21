/** The tabs on a paper's extraction page, in display order. The page
 * reads the open one from the `tab` search param so a link can land on a
 * specific tab (the papers table's Patients / Variants / Flags counts). */
export const EXTRACTION_TABS = [
  'occurrences',
  'families',
  'unassociated-patients',
  'unassociated-variants',
  'flags',
  'figures',
  'paper-metadata',
] as const

export type ExtractionTab = (typeof EXTRACTION_TABS)[number]

export const DEFAULT_EXTRACTION_TAB: ExtractionTab = 'occurrences'

/** Tab values links were written with before a tab was renamed, so those
 * links still open the tab they meant. */
const LEGACY_EXTRACTION_TABS: Record<string, ExtractionTab> = {
  // The Figure Descriptions tab held only the pedigree until 2026-10.
  pedigree: 'figures',
}

export function isExtractionTab(value: unknown): value is ExtractionTab {
  return typeof value === 'string' && (EXTRACTION_TABS as readonly string[]).includes(value)
}

/** The tab a `?tab=` value names, including values from before a rename;
 * undefined when it names none. */
export function parseExtractionTab(value: unknown): ExtractionTab | undefined {
  if (isExtractionTab(value)) return value
  return typeof value === 'string' ? LEGACY_EXTRACTION_TABS[value] : undefined
}
