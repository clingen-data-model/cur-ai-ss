/* Hover text on one element: the app's tooltip, in one line at the call site.
 *
 *   <Hint label="Download PDF">
 *     <Button variant="ghost" size="sm" onClick={download}><Download /></Button>
 *   </Hint>
 *
 * The browser's own `title` attribute was the other way to get hover text,
 * and the app had both: the grey native box on some controls, the dark
 * Tooltip on the rest. Native titles also never show on touch or on
 * keyboard focus. Every hover text now comes through here or through the
 * Tooltip primitives directly, where the content is more than a label.
 *
 * The child is the trigger: Base UI takes it through `render` and merges
 * its own props (ref, handlers, data attributes) into it, so the child must
 * be one element that accepts a ref and spreads unknown props. A DOM
 * element, Button, Badge, Link and TabsTrigger all do.
 *
 * `wrap` makes a span around the child the trigger instead. For a disabled
 * Button, whose pointer events are off: the tooltip saying why it is
 * disabled would otherwise never open.
 *
 * No label, no tooltip: the child renders alone, so a conditional reason
 * (`label={busy ? ... : undefined}`) needs no branching at the call site.
 */
import type { ReactElement, ReactNode } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export function Hint({
  label,
  children,
  wrap = false,
}: {
  label: ReactNode
  children: ReactElement
  wrap?: boolean
}) {
  if (label === undefined || label === null || label === false || label === '') return children
  return (
    <Tooltip>
      {wrap ? (
        <TooltipTrigger render={<span className="inline-flex" />}>{children}</TooltipTrigger>
      ) : (
        <TooltipTrigger render={children} />
      )}
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}
