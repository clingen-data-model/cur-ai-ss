/* lib/models/variant.py's VariantType isn't exposed as an enum in the OpenAPI
 * schema (VariantResp.variant_type is a plain string), so its options are
 * mirrored here by hand. */
export const VARIANT_TYPE_OPTIONS = [
  'Missense',
  'Frameshift',
  'Stop Gained',
  'Splice Donor',
  'Splice Acceptor',
  'Splice Region',
  'Start Lost',
  'Inframe Deletion',
  'Frameshift Deletion',
  'Inframe Insertion',
  'Frameshift Insertion',
  'Structural',
  'Synonymous',
  'Intron',
  "5' UTR",
  "3' UTR",
  'Non-Coding',
  'Unknown',
]
