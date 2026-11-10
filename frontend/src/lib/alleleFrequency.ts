/* gnomAD allele frequencies come back from the annotation agent as raw
 * doubles (0.0000018588304982037502), which read as noise in a detail row.
 * Eight decimal places as a plain decimal (0.00000186), never scientific
 * notation: curators compare these against each other down a column, and
 * 1.85883e-6 next to 0.000254237 asks for a conversion while two decimals
 * of the same width line up by eye. Eight keeps two digits of the rarest
 * frequency gnomAD can report (one allele in about 1.6 million, 6e-7).
 * Zero is a real value (seen, counted, absent) and stays "0".
 */
const DECIMAL_PLACES = 8

export function formatAf(af: number | null | undefined): string | null {
  if (af == null) return null
  if (af === 0) return '0'
  return af.toFixed(DECIMAL_PLACES)
}
