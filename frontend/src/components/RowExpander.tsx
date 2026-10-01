import { ChevronDown, ChevronRight } from 'lucide-react'

/** The caret that opens a row's detail panel. One component so every table
 * that expands rows (occurrences, families, unassociated patients) looks and
 * behaves the same; the click does not reach the row's own click handler. */
export function RowExpander({ expanded, onToggle }: { expanded: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-label={expanded ? 'Collapse row' : 'Expand row'}
      aria-expanded={expanded}
      onClick={(e) => {
        e.stopPropagation()
        onToggle()
      }}
      className="cursor-pointer flex items-center"
    >
      {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
    </button>
  )
}
