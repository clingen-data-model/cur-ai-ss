/** A protein change as shown inside a label's own parentheses.
 *
 * HGVS writes a change predicted from the DNA, not seen in the protein, as
 * "p.(His63Tyr)". Nearly every variant here is DNA-only, so the paper's own
 * parentheses carry little, and wrapping that in the label's "(...)" gave
 * "c.187C>T (p.(His63Tyr))". Drop the inner pair: "p.His63Tyr". Display only --
 * the stored value and the detail panel keep the paper's wording. */
export function displayProteinChange(hgvsP: string): string {
  return hgvsP.replace(/p\.\(([^()]*)\)/g, 'p.$1')
}
