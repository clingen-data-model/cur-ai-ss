/* Read-only quote/reasoning/curator-note viewer, next to an editable or
 * extracted field -- the SPA analog of the Streamlit "Evidence & Reasoning"
 * popover (lib/ui/paper/shared.py's render_evidence_controls). "View in PDF"
 * opens a read-only sheet scrolled to this evidence (see
 * PdfHighlightProvider); there is no color picker or persistent highlighting
 * here, unlike Streamlit's version.
 */
import { FileSearch, Info, TriangleAlert } from 'lucide-react'
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
  // /grobid-annotation to search -- "View in PDF" is not offered for these.
  is_supplement?: boolean
}

const TRIGGER_CLASSNAME =
  'inline-flex items-center justify-center size-6 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed transition-colors'

export function EvidencePopover({ block }: { block?: EvidenceLike | null }) {
  const { openHighlight } = usePdfHighlight()
  const hasContent = !!(block?.quote || block?.reasoning || block?.human_edit_note)
  const canViewInPdf =
    !block?.is_supplement &&
    (!!block?.quote || block?.table_id != null || block?.image_id != null)
  // edited_at is only ever set from a real edits-table row (see
  // _attach_edit_history in app.py), never at initial extraction, so it's a
  // reliable "a human changed this" signal independent of whether a note was
  // left -- though HumanEditNoteDialog forces one for every edit made here.
  const isHumanEdited = !!block?.edited_at

  return (
    <Popover>
      {hasContent ? (
        <Tooltip>
          <TooltipTrigger render={<PopoverTrigger className={TRIGGER_CLASSNAME} />}>
            {isHumanEdited ? (
              <TriangleAlert className="size-3.5 text-orange-500" />
            ) : (
              <Info className="size-3.5" />
            )}
          </TooltipTrigger>
          <TooltipContent>Evidence & Reasoning</TooltipContent>
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
            {block.edited_by_name && (
              <p className="text-xs text-muted-foreground">
                Edited by {block.edited_by_name}
                {block.edited_by_is_active === false ? ' (deactivated)' : ''}
                {block.edited_at ? ` on ${new Date(block.edited_at).toLocaleDateString()}` : ''}
              </p>
            )}
          </div>
        )}
        {canViewInPdf && (
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
                })
              }
            >
              <FileSearch className="size-3.5 mr-1.5" />
              View in PDF
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
