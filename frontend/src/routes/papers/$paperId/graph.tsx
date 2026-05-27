import { useEffect, useRef } from 'react'
import { useParams } from '@tanstack/react-router'
import CytoscapeComponent from 'react-cytoscapejs'
import type { Core } from 'cytoscape'
import type { ElementDefinition } from 'cytoscape'
import { usePaperGraph } from '@/hooks/usePaperGraph'
import { cyStylesheet } from '@/lib/graphElements'

// Compound Spring Embedder - Cytoscape's built-in force-directed layout algorithm
const LAYOUT_ALGORITHM = 'cose'

export function PaperGraphPage() {
  const { paperId } = useParams({ strict: false })
  const { elements, isLoading, isError, error } = usePaperGraph(paperId)
  const cyRef = useRef<Core | null>(null)

  useEffect(() => {
    if (cyRef.current && elements.length > 0) {
      cyRef.current.elements().layout({ name: LAYOUT_ALGORITHM }).run()
    }
  }, [elements])

  const handleCytoscape = (cy: Core) => {
    cyRef.current = cy
    if (elements.length > 0) {
      cy.elements().layout({ name: LAYOUT_ALGORITHM }).run()
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-slate-500">Loading graph...</div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-red-500">Error loading graph: {error?.message || 'Unknown error'}</div>
      </div>
    )
  }

  if (elements.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-slate-500">No data found for this paper</div>
      </div>
    )
  }

  return (
    <div className="w-full" style={{ height: '80vh' }}>
      <CytoscapeComponent
        elements={elements}
        style={{ width: '100%', height: '100%' }}
        stylesheet={cyStylesheet as any}
        cy={handleCytoscape}
      />
    </div>
  )
}
