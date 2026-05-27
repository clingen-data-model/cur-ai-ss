import { useEffect, useRef } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import type { Core } from 'cytoscape'
import type { ElementDefinition } from 'cytoscape'
import { cyStylesheet } from '@/lib/graphElements'

interface PaperGraphProps {
  elements: ElementDefinition[]
  onCyReady?: (cy: Core) => void
}

export function PaperGraph({ elements, onCyReady }: PaperGraphProps) {
  // Store reference to Cytoscape instance so we can access it in effects without recreating the graph
  // cyRef.current is set in handleCytoscape callback when the component mounts
  const cyRef = useRef<Core | null>(null)

  useEffect(() => {
    if (cyRef.current && elements.length > 0) {
      cyRef.current.elements().layout({ name: 'cose' }).run()
    }
  }, [elements])

  // Called when CytoscapeComponent finishes rendering and passes the Cytoscape instance
  const handleCytoscape = (cy: Core) => {
    // Store the Cytoscape instance in ref so useEffect can access it later
    cyRef.current = cy

    if (elements.length > 0) {
      cy.elements().layout({ name: 'cose' }).run()
    }

    onCyReady?.(cy)
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
