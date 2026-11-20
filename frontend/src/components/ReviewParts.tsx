/* Pieces the two keyboard reviews share (HpoReviewDialog.tsx,
 * OccurrenceReviewDialog.tsx): the quote chips, the section labels, the
 * basis text, the key legend, the check that keeps a review's keys out of a
 * field the curator is typing in, and the split between the review and the
 * paper, which can be dragged narrower or folded away. */
import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import type { Citation } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'
import { usePdfHighlight } from '@/components/PdfHighlightProvider'
import { describeAnchor } from '@/lib/anchors'

export function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.isContentEditable ||
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) ||
    // An open select's or menu's options take the keys too.
    target.closest('[role="listbox"], [role="menu"]') !== null
  )
}

/** Whether a dialog is open on top of the review's own (an edit's note, the
 * relink search): the review's keys and its Esc then belong to that one. */
export function dialogAbove(): boolean {
  return document.querySelectorAll('[role="dialog"], [role="alertdialog"]').length > 1
}

/** A review's single-key shortcuts, on the window while `active`. The
 * listener is attached once and calls the latest `actions` through a ref
 * updated in a layout effect, which has run by the time the next key event
 * arrives: a listener re-attached after each render (the first version) let
 * a second key pressed quickly act on the step before the first key's. */
export function useReviewKeys(active: boolean, actions: Record<string, () => void>) {
  const latest = useRef(actions)
  useLayoutEffect(() => {
    latest.current = actions
  })
  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target) || dialogAbove()) return
      const action = latest.current[event.key]
      if (!action) return
      event.preventDefault()
      action()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active])
}

/** The passages a value cites, each a button that highlights it alone. */
export function Quotes({ citations }: { citations: Citation[] }) {
  const { anchorPage, openHighlight } = usePdfHighlight()
  if (citations.length === 0) return <p className="text-muted-foreground">No passage cited.</p>
  return (
    <ul className="space-y-1">
      {citations.map((citation, index) => (
        <li key={`${citation.anchor}-${index}`}>
          <button
            type="button"
            className="flex w-full items-start gap-1.5 rounded text-left hover:bg-muted cursor-pointer"
            onClick={() => openHighlight({ citations: [citation] })}
          >
            <Badge variant="outline" className="shrink-0 font-normal">
              {describeAnchor(citation.anchor, anchorPage(citation.anchor))}
            </Badge>
            {citation.quote && <span className="min-w-0 [overflow-wrap:anywhere]">“{citation.quote}”</span>}
          </button>
        </li>
      ))}
    </ul>
  )
}

export function StepLabel({ step, children }: { step: number; children: ReactNode }) {
  return (
    <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
      <span className="flex size-4 items-center justify-center rounded-full bg-muted text-[10px] text-foreground">
        {step}
      </span>
      {children}
    </p>
  )
}

export function Why({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="break-words">{children}</p>
    </div>
  )
}

export function KeyLegend({ keys }: { keys: [string, string][] }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 border-t px-4 py-2 text-xs text-muted-foreground">
      {keys.map(([key, label]) => (
        <span key={key}>
          <kbd className="rounded border bg-muted px-1 font-mono">{key}</kbd> {label}
        </span>
      ))}
    </div>
  )
}

/** The review beside the paper, with a divider to drag between them. */
export function ReviewSplit({
  review,
  pdf,
  reviewSize = '38%',
}: {
  review: ReactNode
  pdf: ReactNode
  /** The review's starting share of the width. */
  reviewSize?: string
}) {
  return (
    <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1">
      <ResizablePanel defaultSize={reviewSize} minSize="22%" className="flex h-full flex-col">
        {review}
      </ResizablePanel>
      <ResizableHandle withHandle />
      {/* Dragged past its minimum, the paper folds away; dragged back, it
          returns. */}
      <ResizablePanel collapsible collapsedSize={0} minSize="20%" className="flex h-full min-w-0 flex-col">
        {pdf}
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
