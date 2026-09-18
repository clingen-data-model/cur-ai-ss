/* The paper's pedigree image + description, if extraction found one --
 * mirrors lib/ui/paper/patients.py's "Pedigree Image" sub-tab. */
import { useQuery } from '@tanstack/react-query'
import { getPedigreePapersPaperIdPedigreeGet } from '@/api/generated'
import { API_BASE_URL } from '@/lib/api'
import { Spinner } from '@/components/ui/spinner'

const STALE_TIME = 5 * 60 * 1000

export function PedigreeTab({ paperId }: { paperId: number }) {
  const { data: pedigree, isPending } = useQuery({
    queryKey: ['pedigree', paperId],
    queryFn: () => getPedigreePapersPaperIdPedigreeGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  if (isPending) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  if (!pedigree) {
    return <p className="text-sm text-muted-foreground">No pedigree image available.</p>
  }

  return (
    <div className="flex flex-col items-center gap-4 max-w-2xl mx-auto py-2">
      <img
        src={`${API_BASE_URL}${pedigree.image_url}`}
        alt="Pedigree"
        className="max-w-full rounded-lg border"
      />
      <p className="text-sm text-muted-foreground whitespace-pre-wrap">{pedigree.description}</p>
    </div>
  )
}
