import { displayProteinChange } from '@/lib/hgvs'

/** "c.123A>G (p.Arg41Gly)" -- the protein change alongside the genomic/cDNA
 * description, when known; how a variant is named in the Occurrences and
 * Unassociated Variants tables. Omitted when they're the same string:
 * variant_description falls back to hgvs_p itself when no genomic/cDNA
 * notation exists (see get_variant_description in lib/models/variant.py),
 * which would otherwise show "p.Arg41Gly (p.Arg41Gly)". A predicted change
 * "p.(Arg41Gly)" loses its own parentheses (displayProteinChange) so the label
 * does not read "(p.(Arg41Gly))". */
export function VariantLabel({ description, hgvsP }: { description: string; hgvsP?: string | null }) {
  return (
    <>
      {description}
      {hgvsP && hgvsP !== description && (
        <span className="text-muted-foreground"> ({displayProteinChange(hgvsP)})</span>
      )}
    </>
  )
}
