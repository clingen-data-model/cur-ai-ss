/* gnomAD allele frequencies come back from the annotation agent as raw
 * doubles (0.0000018588304982037502), which read as noise in a detail row.
 * Seven significant figures as a plain decimal (0.000001858830), never
 * scientific notation: curators compare these against each other down a
 * column, and 1.85883e-6 next to 0.000254237 asks for a conversion while
 * two decimals line up by eye. Zero is a real value (seen, counted,
 * absent) and stays "0".
 */
const SIGNIFICANT_FIGURES = 7

export function formatAf(af: number | null | undefined): string | null {
  if (af == null) return null
  if (af === 0) return '0'
  // Decimals needed for seven significant figures: toPrecision would switch
  // to scientific notation below 1e-6, where rare gnomAD frequencies live.
  const decimals = SIGNIFICANT_FIGURES - 1 - Math.floor(Math.log10(Math.abs(af)))
  return af.toFixed(Math.min(Math.max(decimals, 0), 100))
}
