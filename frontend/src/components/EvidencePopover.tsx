/* Read-only quote/reasoning/curator-note viewer, next to an editable or
 * extracted field -- the SPA analog of the Streamlit "Evidence & Reasoning"
 * popover (lib/ui/paper/shared.py's render_evidence_controls). "View in PDF"
 * opens a read-only sheet scrolled to this evidence (see
 * PdfHighlightProvider); there is no color picker or persistent highlighting
 * here, unlike Streamlit's version.
 */
import { FileSearch, Info, UserRoundPen } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { usePdfHighlight } from '@/components/PdfHighlightProvider'

export interface EvidenceLike {
  quote?: string | null
  reasoning?: string | null
  human_edit_note?: string | null
  edited_by_name?: string | null
  edited_by_is_active?: boolean | null
  edited_at?: string | null
  table_id?: number | null
  image_id?: number | null
  // Supplement PDFs have no words.json of their own, so there's nothing for
  // /grobid-annotation to search -- the PDF tab is not offered for these, but
  // the Markdown tab (reading the supplement's own raw.md) still is.
  is_supplement?: boolean
  // The current value (`value`) and, when the latest edit's old_value was
  // captured, what it changed from (`previous_value`) -- typed loosely since
  // this interface is shared across every HumanEvidenceBlock<T> variant
  // (str/int/bool/enum/list). previous_value is only present on
  // HumanEvidenceBlock; the other Attributed* blocks carry edited_* alone.
  value?: unknown
  previous_value?: unknown
}

const TRIGGER_CLASSNAME =
  'inline-flex items-center justify-center size-6 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed transition-colors'

function formatEvidenceValue(value: unknown): string {
  if (value == null || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export function EvidencePopover({ block }: { block?: EvidenceLike | null }) {
  const { openHighlight } = usePdfHighlight()
  const hasContent = !!(block?.quote || block?.reasoning || block?.human_edit_note)
  const canViewInPdf =
    !block?.is_supplement &&
    (!!block?.quote || block?.table_id != null || block?.image_id != null)
  // Supplement PDFs have no words.json, so the PDF tab can't locate anything
  // -- but the Markdown tab reads the supplement's own raw.md directly, so a
  // supplement quote can still be shown there.
  const canViewMarkdownOnly = !!block?.is_supplement && !!block?.quote
  const canViewEvidence = canViewInPdf || canViewMarkdownOnly
  // edited_at is only ever set from a real edits-table row (see
  // _attach_edit_history in app.py), never at initial extraction, so it's a
  // reliable "a human changed this" signal independent of whether a note was
  // left -- though HumanEditNoteDialog forces one for every edit made here.
  // That includes values a curator entered at creation: those get an edits
  // row too. Backfilled rows have no user, hence the fallback tooltip text.
  const isHumanEdited = !!block?.edited_at

  return (
    <Popover>
      {hasContent ? (
        <Tooltip>
          <TooltipTrigger render={<PopoverTrigger className={TRIGGER_CLASSNAME} />}>
            {isHumanEdited ? (
              <UserRoundPen className="size-3.5 text-orange-500" />
            ) : (
              <Info className="size-3.5" />
            )}
          </TooltipTrigger>
          <TooltipContent
            className={isHumanEdited ? 'bg-orange-500 text-white' : undefined}
            arrowClassName={isHumanEdited ? 'bg-orange-500 fill-orange-500' : undefined}
          >
            {isHumanEdited
              ? block?.edited_by_name
                ? `Edited by ${block.edited_by_name}`
                : 'Manually entered by curator'
              : 'Evidence & Reasoning'}
          </TooltipContent>
        </Tooltip>
      ) : (
        <PopoverTrigger disabled className={TRIGGER_CLASSNAME}>
          <Info className="size-3.5" />
        </PopoverTrigger>
      )}
      <PopoverContent className="w-80 text-sm space-y-2">
        {block?.quote && (
          <p className="break-words">
            <span className="font-medium">Evidence: </span>
            {block.quote}
          </p>
        )}
        {block?.reasoning && (
          <p className="break-words">
            <span className="font-medium">Reasoning: </span>
            {block.reasoning}
          </p>
        )}
        {block?.human_edit_note && (
          <div className="pt-2 border-t space-y-0.5">
            <p className="font-medium">Curator Note</p>
            <p className="text-muted-foreground break-words">{block.human_edit_note}</p>
            {block.previous_value != null && (
              <p className="text-xs text-muted-foreground break-words">
                Changed from <span className="font-medium">{formatEvidenceValue(block.previous_value)}</span> to{' '}
                <span className="font-medium">{formatEvidenceValue(block.value)}</span>
              </p>
            )}
            {block.edited_by_name && (
              <p className="text-xs text-muted-foreground">
                Edited by {block.edited_by_name}
                {block.edited_by_is_active === false ? ' (deactivated)' : ''}
                {block.edited_at ? ` on ${new Date(block.edited_at).toLocaleDateString()}` : ''}
              </p>
            )}
          </div>
        )}
        {canViewEvidence && (
          <div className="pt-2 border-t">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() =>
                openHighlight({
                  quote: block?.quote,
                  table_id: block?.table_id,
                  image_id: block?.image_id,
                  is_supplement: block?.is_supplement,
                })
              }
            >
              <FileSearch className="size-3.5 mr-1.5" />
              {canViewInPdf ? 'View in PDF' : 'View in Markdown'}
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
