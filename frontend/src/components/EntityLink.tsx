import type * as React from 'react'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'

/** Patient/Variant cell: click expands the row's detail panel, hover previews
 * a snippet of it (demographics / ClinVar+gnomAD) without expanding. */
export function EntityLink({
  onClick,
  hoverContent,
  children,
}: {
  onClick: () => void
  hoverContent: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <HoverCard>
      <HoverCardTrigger
        render={<button type="button" />}
        onClick={(e) => {
          e.stopPropagation()
          onClick()
        }}
        className="text-left hover:underline underline-offset-2 cursor-pointer"
      >
        {children}
      </HoverCardTrigger>
      <HoverCardContent className="w-72">{hoverContent}</HoverCardContent>
    </HoverCard>
  )
}
