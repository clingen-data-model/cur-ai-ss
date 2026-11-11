/* External reference links for a variant, shared between VariantDetailPanel
 * (Harmonized and Annotations tabs) and the Occurrences table's variant hover
 * card.
 *
 * Coordinates are gnomAD-style "CHROM-POS-REF-ALT" as harmonization writes
 * them. Harmonization takes the Allele Registry's GRCh38 allele whenever
 * there is one and annotation looks them up in gnomAD v4, so every coordinate
 * link below names GRCh38 / hg38. */

export interface ExternalLink {
  label: string
  href: string
}

export function gnomadUrl(coordinates: string): string {
  return `https://gnomad.broadinstitute.org/variant/${coordinates}?dataset=gnomad_r4`
}

export function clinGenUrl(caid: string): string {
  return `https://reg.clinicalgenome.org/redmine/projects/registry/genboree_registry/by_canonicalid?canonicalid=${caid}`
}

export function dbSnpUrl(rsid: string): string {
  return `https://www.ncbi.nlm.nih.gov/snp/${encodeURIComponent(rsid)}`
}

/** The ClinVar record annotation took its classification from, when the
 * annotation kept its variation ID. */
export function clinVarRecordUrl(variationId: string): string {
  return `https://www.ncbi.nlm.nih.gov/clinvar/variation/${encodeURIComponent(variationId)}/`
}

/** A ClinVar search, for annotations from before the variation ID was kept.
 * It can list more than one record (an rsID may cover several alleles). */
export function clinVarSearchUrl(term: string): string {
  return `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(term)}`
}

/** Broad's SpliceAI Lookup, opened on the variant with its default settings. */
export function spliceAiLookupUrl(coordinates: string): string {
  return `https://spliceailookup.broadinstitute.org/#variant=${encodeURIComponent(coordinates)}&hg=38&bc=basic&distance=500&mask=0&ra=0`
}

/** Ensembl's variant page; it carries VEP's consequences on every transcript.
 * Ensembl has no page for a VEP result itself, so this needs an rsID. */
export function ensemblVariantUrl(rsid: string): string {
  return `https://www.ensembl.org/Homo_sapiens/Variation/Explore?v=${encodeURIComponent(rsid)}`
}

/** UCSC Genome Browser on hg38 at the variant's position, or null when the
 * coordinates are not gnomAD-style. */
export function ucscUrl(coordinates: string): string | null {
  // Colons too: a curator-edited value may be written 17:41196312:AG:A.
  const match = /^(?:chr)?([0-9XYM]+|MT)[-:](\d+)[-:]([ACGTN]+)[-:]([ACGTN]+)$/i.exec(coordinates)
  if (!match) return null
  const [, chrom, pos, ref] = match
  const start = Number(pos)
  const end = start + ref.length - 1
  const ucscChrom = chrom.toUpperCase() === 'MT' ? 'M' : chrom.toUpperCase()
  return `https://genome.ucsc.edu/cgi-bin/hgTracks?db=hg38&position=chr${ucscChrom}:${start}-${end}`
}

/** The identifiers an annotation was looked up with, which is what its links
 * are built from: a curator can edit the harmonized fields without
 * re-annotating, and the links should lead to where the numbers came from. */
export interface AnnotationIds {
  gnomad_style_coordinates?: string | null
  rsid?: string | null
  caid?: string | null
  clinvar_variation_id?: string | null
}

export function clinVarLinks(ids: AnnotationIds): ExternalLink[] {
  const links: ExternalLink[] = []
  if (ids.clinvar_variation_id) {
    links.push({ label: 'ClinVar', href: clinVarRecordUrl(ids.clinvar_variation_id) })
  } else if (ids.rsid || ids.caid) {
    links.push({ label: 'Search ClinVar', href: clinVarSearchUrl((ids.rsid ?? ids.caid) as string) })
  }
  if (ids.rsid) links.push({ label: 'dbSNP', href: dbSnpUrl(ids.rsid) })
  return links
}

export function inSilicoLinks(ids: AnnotationIds): ExternalLink[] {
  const links: ExternalLink[] = []
  if (ids.gnomad_style_coordinates) {
    links.push({ label: 'SpliceAI Lookup', href: spliceAiLookupUrl(ids.gnomad_style_coordinates) })
  }
  if (ids.rsid) links.push({ label: 'Ensembl', href: ensemblVariantUrl(ids.rsid) })
  return links
}

export function populationLinks(ids: AnnotationIds): ExternalLink[] {
  const coords = ids.gnomad_style_coordinates
  if (!coords) return []
  const links: ExternalLink[] = [{ label: 'gnomAD', href: gnomadUrl(coords) }]
  const ucsc = ucscUrl(coords)
  if (ucsc) links.push({ label: 'UCSC (hg38)', href: ucsc })
  return links
}
