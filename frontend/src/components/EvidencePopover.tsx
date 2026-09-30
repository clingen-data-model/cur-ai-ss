/* Read-only citations/reasoning/curator-note viewer, next to an editable or
 * extracted field -- the SPA analog of the Streamlit "Evidence & Reasoning"
 * popover (lib/ui/paper/shared.py's render_evidence_controls). "View in PDF"
 * opens a read-only sheet scrolled to this evidence (see
 * PdfHighlightProvider); there is no color picker or persistent highlighting
 * here, unlike Streamlit's version.
 */
import { FileSearch, Info, UserRoundPen } from 'lucide-react'
import type { Citation } from '@/api/generated'
import { describeAnchor, isSupplementAnchor } from '@/lib/anchors'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePdfHighlight } from '@/components/PdfHighlightProvider'

export interface EvidenceLike {
  // Where the value comes from: one {anchor, quote} per block of the paper it
  // rests on (docs/evidence-anchors-plan.md). Optional because a few callers
  // synthesize note-only or reasoning-only blocks that carry none.
  citations?: Citation[] | null
  reasoning?: string | null
  human_edit_note?: string | null
  edited_by_name?: string | null
  edited_by_is_active?: boolean | null
  edited_at?: string | null
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
  const citations = block?.citations ?? []
  const hasContent = !!(citations.length || block?.reasoning || block?.human_edit_note)
  const canViewEvidence = citations.length > 0
  // Supplement citations have no PDF view of their own (see
  // PdfHighlightProvider's isSupplementOnly), so evidence resting entirely on
  // the supplement gets a "View in Markdown" button instead of "View in PDF".
  const viewInPdf = citations.some((citation) => !isSupplementAnchor(citation.anchor))
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
        {citations.length > 0 && (
          <div className="space-y-1">
            <p className="font-medium">Evidence</p>
            <ul className="space-y-1">
              {citations.map((citation, index) => (
                <li key={`${citation.anchor}-${index}`} className="flex items-start gap-1.5">
                  <Badge variant="outline" className="shrink-0 font-normal" title={citation.anchor}>
                    {describeAnchor(citation.anchor)}
                  </Badge>
                  {/* min-w-0 lets the flex item shrink below its content width and
                      overflow-wrap:anywhere breaks a quote with no spaces (an HGVS
                      string, an accession), which break-words alone leaves overflowing
                      the card. */}
                  {/* No quote means the whole block (a figure never has one): the
                      badge already says which, so nothing else is shown. */}
                  {citation.quote && (
                    <span className="min-w-0 [overflow-wrap:anywhere]">“{citation.quote}”</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
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
              onClick={() => openHighlight({ citations })}
            >
              <FileSearch className="size-3.5 mr-1.5" />
              {viewInPdf ? 'View in PDF' : 'View in Markdown'}
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
