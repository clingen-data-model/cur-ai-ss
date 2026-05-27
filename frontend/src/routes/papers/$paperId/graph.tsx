import { useParams } from '@tanstack/react-router'
import { usePaperGraph } from '@/hooks/usePaperGraph'
import { PaperGraph } from '@/components/PaperGraph'

export function PaperGraphPage() {
  const { paperId } = useParams({ strict: false })
  const { elements, isLoading, isError, error } = usePaperGraph(paperId)

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

  return <PaperGraph elements={elements} />
}
