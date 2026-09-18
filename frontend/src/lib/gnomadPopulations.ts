/* gnomAD v4 genetic ancestry group IDs mapped to their full names, mirroring
 * lib/ui/paper/shared.py's GNOMAD_POPULATION_NAMES / format_gnomad_population. */
const GNOMAD_POPULATION_NAMES: Record<string, string> = {
  afr: 'African/African American',
  ami: 'Amish',
  amr: 'Admixed American',
  asj: 'Ashkenazi Jewish',
  eas: 'East Asian',
  fin: 'European (Finnish)',
  nfe: 'European (non-Finnish)',
  mid: 'Middle Eastern',
  sas: 'South Asian',
  remaining: 'Remaining',
}

/** Render a gnomAD population id as its full name, e.g. `nfe` -> `European (non-Finnish) (nfe)`. */
export function formatGnomadPopulation(population: string | null | undefined): string {
  if (!population) return 'N/A'
  const fullName = GNOMAD_POPULATION_NAMES[population.toLowerCase()]
  return fullName ? `${fullName} (${population})` : population
}
