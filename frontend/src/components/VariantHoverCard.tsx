/* Small "at a glance" annotation snippet for the Occurrences table's
 * Variant column hover card -- ClinVar/gnomAD/gnomAD-style id, in the spirit
 * of the pptx curation export's variant summary (lib/misc/curation/summary.py). */
import type { VariantResp } from '@/api/generated/types.gen'
import { gnomadUrl, clinGenUrl } from '@/lib/variantLinks'
import { formatGnomadPopulation } from '@/lib/gnomadPopulations'

function formatAf(af: number | null | undefined): string | null {
  if (af == null) return null
  return af === 0 ? '0' : af.toExponential(2)
}

export function VariantHoverCardContent({ variant }: { variant: VariantResp }) {
  const harmonized = variant.harmonized_variant.value
  const annotated = variant.annotated_variant
  const gnomadCoords = harmonized?.gnomad_style_coordinates
  const caid = harmonized?.caid ?? variant.caid

  const popmaxAf = formatAf(annotated?.gnomad_popmax_af)
  const topLevelAf = formatAf(annotated?.gnomad_top_level_af)

  return (
    <div className="space-y-1.5">
      <p className="font-semibold truncate">{variant.variant_description}</p>

      {(gnomadCoords || caid) && (
        <div className="flex items-center justify-between gap-2">
          {gnomadCoords && (
            <a
              href={gnomadUrl(gnomadCoords)}
              target="_blank"
              rel="noreferrer"
              className="truncate font-mono text-xs text-primary hover:underline"
            >
              {gnomadCoords}
            </a>
          )}
          {caid && (
            <a
              href={clinGenUrl(caid)}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 font-mono text-xs text-primary hover:underline"
            >
              {caid}
            </a>
          )}
        </div>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs">
        <dt className="text-muted-foreground">ClinVar</dt>
        <dd className="text-right truncate">
          {annotated?.pathogenicity
            ? `${annotated.pathogenicity}${
                annotated.stars != null ? ` (${'⭐'.repeat(annotated.stars) || '0⭐'})` : ''
              }`
            : caid
              ? 'Not in ClinVar'
              : 'N/A'}
        </dd>

        <dt className="text-muted-foreground">gnomAD</dt>
        <dd className="text-right truncate">
          {popmaxAf
            ? `${popmaxAf}${
                annotated?.gnomad_popmax_population
                  ? ` — ${formatGnomadPopulation(annotated.gnomad_popmax_population)}`
                  : ''
              }`
            : (topLevelAf ?? 'Not found')}
        </dd>

        {annotated?.revel != null && (
          <>
            <dt className="text-muted-foreground">REVEL</dt>
            <dd className="text-right">{annotated.revel.toFixed(3)}</dd>
          </>
        )}
      </dl>
    </div>
  )
}
