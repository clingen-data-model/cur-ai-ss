/* Helpers for rendering a paper's extracted markdown with an evidence quote
 * highlighted (see DocumentEvidenceViewer.tsx, the evidence sheet's
 * "Markdown" tab).
 *
 * A literal `<mark>` is spliced into the markdown source at the match's
 * offsets before rendering. rehype-raw is what lets ReactMarkdown treat that
 * as an element rather than literal text; rehype-sanitize (GitHub's default
 * schema, plus `mark`) keeps that raw-HTML door from also admitting anything
 * unexpected already sitting in a paper's markdown (Docling table conversion
 * can leave stray literal HTML in raw.md, the same reason
 * lib/models/evidence_block.py strips markup from quotes shown elsewhere in
 * the UI).
 *
 * Matching is a whitespace-tolerant exact match only, no fuzzy fallback: a
 * citation's quote is copied verbatim from the paper, but Docling's markdown
 * export can reproduce a justified PDF's text layer with runs of 2+ raw
 * spaces between words that a verbatim quote collapses to one (confirmed on
 * paper 27, PMID 8675681: "extended  kindred" in raw.md vs. "extended
 * kindred" in the quote) -- so the quote's own whitespace runs are matched
 * loosely while everything else must line up exactly.
 */
import { defaultSchema } from 'rehype-sanitize'
import { API_BASE_URL } from '@/lib/api'

export const SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'mark'],
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export interface TextMatch {
  start: number
  end: number
}

export function findWhitespaceTolerantMatch(quote: string | null | undefined, text: string): TextMatch | null {
  const trimmed = quote?.trim()
  if (!trimmed || !text) return null
  const pattern = trimmed.split(/\s+/).map(escapeRegExp).join('\\s+')
  const match = new RegExp(pattern, 'i').exec(text)
  return match ? { start: match.index, end: match.index + match[0].length } : null
}

export function withHighlight(content: string, match: TextMatch | null): string {
  if (!match) return content
  return content.slice(0, match.start) + '<mark>' + content.slice(match.start, match.end) + '</mark>' + content.slice(match.end)
}

/* Docling writes each figure's `src` as the absolute filesystem path it saved
 * the image to on the API host (e.g. `/var/caa/extracted_pdfs/20/raw_artifacts/
 * image_000002_<hash>.png`) -- the same kind of server-relative path the API
 * returns for thumbnail_url/pdf_url/avatar_url, which every other caller in
 * this app resolves by prefixing API_BASE_URL (see PedigreeTab.tsx). Left
 * alone, the browser instead resolves it against the SPA's own origin.
 */
export function resolveImageSrc(src: string | undefined): string | undefined {
  return src?.startsWith('/') ? `${API_BASE_URL}${src}` : src
}
