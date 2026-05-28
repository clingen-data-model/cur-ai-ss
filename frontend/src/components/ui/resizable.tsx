import * as React from 'react'
import { GripVertical } from 'lucide-react'
import {
  Group,
  Panel,
  Separator,
} from 'react-resizable-panels'

const ResizablePanelGroup = React.forwardRef<
  any,
  React.ComponentPropsWithoutRef<typeof Group>
>(({ ...props }, ref) => <Group groupRef={ref} {...props} />)
ResizablePanelGroup.displayName = 'ResizablePanelGroup'

const ResizablePanel = Panel as any
ResizablePanel.displayName = 'ResizablePanel'

const ResizableHandle = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof Separator> & {
    withHandle?: boolean
  }
>(({ withHandle, ...props }, ref) => (
  <Separator
    elementRef={ref}
    {...props}
    className={`relative flex w-px select-none touch-none bg-border after:absolute after:left-1/2 after:top-1/2 after:h-8 after:w-1 after:-translate-x-1/2 after:-translate-y-1/2 after:translate-x-0 after:bg-border after:opacity-0 hover:after:opacity-100 after:transition-opacity [&[data-panel-group-direction=vertical]]:h-px [&[data-panel-group-direction=vertical]]:w-full [&[data-panel-group-direction=vertical]]:after:h-1 [&[data-panel-group-direction=vertical]]:after:w-8 ${props.className || ''}`}
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
