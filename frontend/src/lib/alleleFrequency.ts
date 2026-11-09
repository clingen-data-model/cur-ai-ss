/* gnomAD allele frequencies come back from the annotation agent as raw
 * doubles (0.0000018588304982037502), which read as noise in a detail row.
 * Six significant figures in scientific notation keeps the precision a
 * curator might compare against gnomAD's page while giving every AF the
 * same width. Zero is a real value (seen, counted, absent) and stays "0".
 */
export function formatAf(af: number | null | undefined): string | null {
  if (af == null) return null
  return af === 0 ? '0' : af.toExponential(5)
}
