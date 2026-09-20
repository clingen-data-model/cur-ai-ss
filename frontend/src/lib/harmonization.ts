/* Port of lib/models/variant.py's is_harmonized/malformed_identifiers --
 * flags a variant whose harmonization produced nothing usable, or produced
 * identifiers that look copied from the paper rather than normalized. Keep
 * this in sync with that file; the two are not derived from a shared source.
 */
import type { HarmonizedVariantResp } from '@/api/generated/types.gen'

type HarmonizedLike = HarmonizedVariantResp | null | undefined

// hgvs_p is deliberately excluded: a protein change alone cannot be
// annotated against gnomAD, ClinVar or VEP, which is why variant annotation
// skips these rows.
const HARMONIZED_IDENTIFIER_FIELDS = [
  'gnomad_style_coordinates',
  'rsid',
  'caid',
  'hgvs_g',
  'hgvs_c',
] as const

// Every HGVS c./g. description names the change with one of these. A string
// without any of them is not HGVS -- usually legacy notation that puts the
// reference base before the position, or a quote the PDF mangled.
const HGVS_CHANGE_OPERATORS = ['>', 'del', 'dup', 'ins', 'inv', 'con', '='] as const

// Checked for whitespace: no identifier in any of these notations contains a
// space, so one means the value was copied out of a broken table cell.
const UNSPACED_IDENTIFIER_FIELDS = [...HARMONIZED_IDENTIFIER_FIELDS, 'hgvs_p'] as const

/** True if harmonization produced at least one usable identifier. */
export function isHarmonized(harmonized: HarmonizedLike): boolean {
  if (!harmonized) return false
  return HARMONIZED_IDENTIFIER_FIELDS.some((field) => harmonized[field])
}

/** Harmonized identifiers that are not well-formed, keyed by field name.
 * Empty when every identifier present looks right, so a non-empty result is
 * the warning. */
export function malformedIdentifiers(harmonized: HarmonizedLike): Record<string, string> {
  if (!harmonized) return {}

  const malformed: Record<string, string> = {}
  for (const field of UNSPACED_IDENTIFIER_FIELDS) {
    const value = harmonized[field]
    if (value && /\s/.test(value)) malformed[field] = value
  }

  for (const field of ['hgvs_c', 'hgvs_g'] as const) {
    const value = harmonized[field]
    if (!value || field in malformed) continue
    if (!HGVS_CHANGE_OPERATORS.some((operator) => value.includes(operator))) {
      malformed[field] = value
    }
  }

  return malformed
}

/** The warning message for a variant's harmonized identifiers, or null when
 * there's nothing to flag. Mirrors lib/ui/paper/variants.py's two warning
 * strings exactly, but points at the paper-level Rerun Agent dialog instead
 * of a per-variant "Re-harmonize" button, which the SPA doesn't have yet. */
export function harmonizationWarning(harmonized: HarmonizedLike): string | null {
  if (!isHarmonized(harmonized)) {
    return (
      'Harmonization produced no gnomAD coordinates, rsID, CAID or HGVS g./c. ' +
      'for this variant, so it could not be annotated. Rerun Variant ' +
      'Harmonization for this paper to try again.'
    )
  }

  const malformed = malformedIdentifiers(harmonized)
  const fields = Object.entries(malformed)
  if (fields.length === 0) return null

  const fieldList = fields.map(([field, value]) => `${field} = "${value}"`).join(', ')
  return (
    `Harmonized notation looks malformed (${fieldList}). It was most likely ` +
    'copied from the paper rather than normalized, so any annotation for ' +
    'this variant may be wrong. Rerun Variant Harmonization for this paper ' +
    'to try again.'
  )
}
