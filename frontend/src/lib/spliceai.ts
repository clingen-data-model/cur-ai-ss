/* Display form of the SpliceAI block the annotation agent stores: the
 * largest of VEP's four delta scores, which site it is, and where that site
 * sits relative to the variant (lib/models/variant.py's SpliceAI.from_raw). */
import type { SpliceAi } from '@/api/generated/types.gen'

const EFFECTS: Record<string, string> = {
  DS_AG: 'acceptor gain',
  DS_AL: 'acceptor loss',
  DS_DG: 'donor gain',
  DS_DL: 'donor loss',
}

/** "0.870 donor loss @ +3", or just the score when VEP gave no site. */
export function formatSpliceAI(spliceai: SpliceAi | null | undefined): string | null {
  if (!spliceai) return null
  const parts = [(spliceai.max_score ?? 0).toFixed(3)]
  if (spliceai.effect_type) parts.push(EFFECTS[spliceai.effect_type] ?? spliceai.effect_type)
  if (spliceai.position != null) {
    parts.push(`@ ${spliceai.position > 0 ? '+' : ''}${spliceai.position}`)
  }
  return parts.join(' ')
}
