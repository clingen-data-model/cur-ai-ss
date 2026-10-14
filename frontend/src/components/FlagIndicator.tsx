/* Row-level curator-flag marker, the third entry in the row-icon language
 * next to ManuallyCreatedIndicator (orange: a human made this) and
 * EvidencePopover (grey: here is the evidence). Violet flag: an agent made a
 * call here a curator should check. Muted once every flag on the row is
 * resolved, and absent when the row has none.
 *
 * Clicking opens the flags themselves -- agent, subject, reasoning, the
 * citations with "View in PDF", and the resolution or a Resolve button. The
 * "keep" half of review lives here; the "delete" half is the row's own
 * trashcan, since deleting the row takes its flags with it.
 */
import { useState } from 'react'
import { FileSearch, Flag } from 'lucide-react'
import type { FlagResp } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { usePdfHighlight } from '@/components/PdfHighlightProvider'
import { ResolveFlagDialog } from '@/components/ResolveFlagDialog'
import { useResolveFlag } from '@/hooks/usePaperFlags'
import { describeAnchor, isSupplementAnchor } from '@/lib/anchors'
import { flagSourceLabel, sortFlags } from '@/lib/flags'

const TRIGGER_CLASSNAME =
  'inline-flex items-center justify-center size-6 rounded hover:bg-muted cursor-pointer transition-colors'

/** One flag, laid out the same way everywhere it is shown (row popover and
 * the Flags tab). `onResolve` is omitted where resolving is not offered. */
export function FlagCard({ flag, onResolve }: { flag: FlagResp; onResolve?: (flag: FlagResp) => void }) {
  const { openHighlight, anchorPage } = usePdfHighlight()
  const citations = flag.evidence.citations ?? []
  const open = flag.resolved_at == null
  const viewInPdf = citations.some((citation) => !isSupplementAnchor(citation.anchor))

  return (
    <div className="space-y-1.5 text-sm">
      <div className="flex items-start gap-2">
        <Flag className={`size-3.5 mt-0.5 shrink-0 ${open ? 'text-violet-600' : 'text-muted-foreground'}`} />
        <div className="min-w-0 flex-1">
          <p className="font-medium break-words">{flag.subject}</p>
          <p className="text-xs text-muted-foreground">{flagSourceLabel(flag)}</p>
        </div>
      </div>
      {flag.evidence.reasoning && <p className="break-words">{flag.evidence.reasoning}</p>}
      {citations.length > 0 && (
        <ul className="space-y-1">
          {citations.map((citation, index) => (
            <li key={`${citation.anchor}-${index}`} className="flex items-start gap-1.5">
              <Badge variant="outline" className="shrink-0 font-normal" title={citation.anchor}>
                {describeAnchor(citation.anchor, anchorPage(citation.anchor))}
              </Badge>
              {citation.quote && <span className="min-w-0 [overflow-wrap:anywhere]">“{citation.quote}”</span>}
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <div className="flex items-center gap-2 pt-1">
          {onResolve && (
            <Button size="sm" onClick={() => onResolve(flag)}>
              Resolve
            </Button>
          )}
          {citations.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => openHighlight({ citations })}>
              <FileSearch className="size-3.5 mr-1.5" />
              {viewInPdf ? 'View in PDF' : 'View in Markdown'}
            </Button>
          )}
        </div>
      ) : (
        <div className="pt-1 border-t space-y-0.5">
          <p className="text-muted-foreground break-words">{flag.resolution_note || 'Resolved without a note'}</p>
          <p className="text-xs text-muted-foreground">
            Resolved{flag.resolved_by ? ` by ${flag.resolved_by.name}` : ''}
            {flag.resolved_at ? ` on ${new Date(flag.resolved_at).toLocaleDateString()}` : ''}
          </p>
        </div>
      )}
    </div>
  )
}

export function FlagIndicator({ paperId, flags }: { paperId: number; flags: FlagResp[] }) {
  const [resolving, setResolving] = useState<FlagResp | null>(null)
  const resolve = useResolveFlag(paperId)

  if (flags.length === 0) return null
  const sorted = sortFlags(flags)
  const openCount = sorted.filter((f) => f.resolved_at == null).length
  const label =
    openCount > 0
      ? `${openCount} open flag${openCount === 1 ? '' : 's'}`
      : `${sorted.length} resolved flag${sorted.length === 1 ? '' : 's'}`

  return (
    <>
      <Popover>
        <Tooltip>
          <TooltipTrigger
            render={<PopoverTrigger className={TRIGGER_CLASSNAME} onClick={(e) => e.stopPropagation()} />}
          >
            <Flag className={`size-3.5 ${openCount > 0 ? 'text-violet-600' : 'text-muted-foreground'}`} />
          </TooltipTrigger>
          <TooltipContent
            className={openCount > 0 ? 'bg-violet-600 text-white' : undefined}
            arrowClassName={openCount > 0 ? 'bg-violet-600 fill-violet-600' : undefined}
          >
            {label}
          </TooltipContent>
        </Tooltip>
        <PopoverContent className="w-96 max-h-[70vh] overflow-y-auto space-y-3" onClick={(e) => e.stopPropagation()}>
          {sorted.map((flag, index) => (
            <div key={flag.id} className={index > 0 ? 'pt-3 border-t' : undefined}>
              <FlagCard flag={flag} onResolve={setResolving} />
            </div>
          ))}
        </PopoverContent>
      </Popover>
      <ResolveFlagDialog
        flag={resolving}
        open={resolving !== null}
        onOpenChange={(open) => {
          if (!open) setResolving(null)
        }}
        isPending={resolve.isPending}
        onConfirm={(note) => {
          if (!resolving) return
          resolve.mutate({ flagId: resolving.id, note }, { onSuccess: () => setResolving(null) })
        }}
      />
    </>
  )
}
