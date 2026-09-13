import * as React from 'react'
import { GripVertical } from 'lucide-react'
import {
  Group,
  type GroupImperativeHandle,
  Panel,
  Separator,
} from 'react-resizable-panels'

const ResizablePanelGroup = React.forwardRef<
  GroupImperativeHandle,
  React.ComponentPropsWithoutRef<typeof Group>
>(({ ...props }, ref) => <Group groupRef={ref} {...props} />)
ResizablePanelGroup.displayName = 'ResizablePanelGroup'

// Re-exported as-is. It was `Panel as any` so a displayName could be attached,
// which cost every caller its prop types to gain a label React DevTools already
// infers from the function's name.
const ResizablePanel = Panel

const ResizableHandle = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof Separator> & {
    withHandle?: boolean
  }
>(({ withHandle, ...props }, ref) => (
  <Separator
    elementRef={ref}
    {...props}
    className={`relative flex w-1 select-none touch-none bg-border hover:bg-slate-400 transition-colors after:absolute after:left-1/2 after:top-1/2 after:h-8 after:w-1.5 after:-translate-x-1/2 after:-translate-y-1/2 after:translate-x-0 after:bg-slate-400 after:opacity-0 hover:after:opacity-100 after:transition-opacity ${props.className || ''}`}
  >
    {withHandle && (
      <div className="z-10 flex h-4 w-4 items-center justify-center rounded-md border bg-border">
        <GripVertical className="h-2.5 w-2.5" />
      </div>
    )}
  </Separator>
))
ResizableHandle.displayName = 'ResizableHandle'

export { ResizablePanelGroup, ResizablePanel, ResizableHandle }
