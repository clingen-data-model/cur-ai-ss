/* External reference links for a harmonized variant, shared between
 * VariantDetailPanel's harmonized tab and the Occurrences table's variant
 * hover card. */
export function gnomadUrl(coordinates: string): string {
  return `https://gnomad.broadinstitute.org/variant/${coordinates}?dataset=gnomad_r4`
}

export function clinGenUrl(caid: string): string {
  return `https://reg.clinicalgenome.org/redmine/projects/registry/genboree_registry/by_canonicalid?canonicalid=${caid}`
}
