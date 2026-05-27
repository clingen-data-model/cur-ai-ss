import { useEffect, useRef } from 'react'
import { useParams } from '@tanstack/react-router'
import CytoscapeComponent from 'react-cytoscapejs'
import type { Core } from 'cytoscape'
import type { ElementDefinition } from 'cytoscape'
import { usePaperGraph } from '@/hooks/usePaperGraph'
import { cyStylesheet } from '@/lib/graphElements'

// Compound Spring Embedder - Cytoscape's built-in force-directed layout algorithm
// Creates a physics-based layout where nodes repel each other like magnets
const LAYOUT_ALGORITHM = 'cose'

export function PaperGraphPage() {
  // Extract paperId from URL route (e.g., /papers/1/graph → paperId = '1')
  const { paperId } = useParams({ strict: false })

  // Fetch all graph data (families, patients, variants, phenotypes) via TanStack Query
  // Returns: nodes/edges for Cytoscape, loading/error states
  const { elements, isLoading, isError, error } = usePaperGraph(paperId)

  // Store reference to Cytoscape instance so we can call methods on it
  // (layout, zoom, pan, etc.) without recreating the entire graph
  const cyRef = useRef<Core | null>(null)

  // Run layout whenever elements load or change
  // By the time this runs, cyRef will have been set by the cy callback
  useEffect(() => {
    if (cyRef.current && elements.length > 0) {
      cyRef.current.elements().layout({ name: LAYOUT_ALGORITHM }).run()
    }
  }, [elements])

  // Show loading spinner while fetching data from API
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-slate-500">Loading graph...</div>
      </div>
    )
  }

  // Show error message if API call failed
  if (isError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-red-500">Error loading graph: {error?.message || 'Unknown error'}</div>
      </div>
    )
  }

  // Show empty state if paper has no families/patients/variants/phenotypes
  if (elements.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-slate-500">No data found for this paper</div>
      </div>
    )
  }

  // Render the actual graph visualization
  return (
    <div className="w-full" style={{ height: '80vh' }}>
      <CytoscapeComponent
        // Pass nodes/edges converted from API data
        elements={elements}
        // Set container to full width/height
        style={{ width: '100%', height: '100%' }}
        // Pass Cytoscape stylesheet (colors, shapes, sizes, etc.)
        // 'as any' bypasses TypeScript type checking (workaround for type mismatch)
        stylesheet={cyStylesheet as any}
        // Callback when Cytoscape renders - save the instance reference for useEffect
        cy={(cy) => {
          cyRef.current = cy
        }}
      />
    </div>
  )
}
