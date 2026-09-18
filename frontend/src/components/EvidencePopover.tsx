/* Read-only quote/reasoning/curator-note viewer, next to an editable or
 * extracted field -- the SPA analog of the Streamlit "Evidence & Reasoning"
 * popover (lib/ui/paper/shared.py's render_evidence_controls), minus the
 * color-picker/highlight controls, since PDF highlighting isn't wired up here yet.
 */
import { MessageSquareQuote } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export interface EvidenceLike {
  quote?: string | null
  reasoning?: string | null
  human_edit_note?: string | null
  edited_by_name?: string | null
  edited_at?: string | null
}

export function EvidencePopover({ block }: { block?: EvidenceLike | null }) {
  const hasContent = !!(block?.quote || block?.reasoning || block?.human_edit_note)

  return (
    <Popover>
      <PopoverTrigger
        disabled={!hasContent}
        className="inline-flex items-center justify-center size-6 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        title="Evidence & Reasoning"
      >
        <MessageSquareQuote className="size-3.5" />
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm space-y-2">
        {block?.quote && (
          <p>
            <span className="font-medium">Evidence: </span>
            {block.quote}
          </p>
        )}
        {block?.reasoning && (
          <p>
            <span className="font-medium">Reasoning: </span>
            {block.reasoning}
          </p>
        )}
        {block?.human_edit_note && (
          <div className="pt-2 border-t space-y-0.5">
            <p className="font-medium">Curator Note</p>
            <p className="text-muted-foreground">{block.human_edit_note}</p>
            {block.edited_by_name && (
              <p className="text-xs text-muted-foreground">
                Edited by {block.edited_by_name}
                {block.edited_at ? ` on ${new Date(block.edited_at).toLocaleDateString()}` : ''}
              </p>
            )}
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
