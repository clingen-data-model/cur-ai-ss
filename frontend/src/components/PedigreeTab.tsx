/* The paper's pedigree image + description, if extraction found one --
 * mirrors lib/ui/paper/patients.py's "Pedigree Image" sub-tab. */
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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
      <div
        className="w-full text-sm text-muted-foreground
          [&_h1]:text-base [&_h1]:font-semibold [&_h1]:text-foreground [&_h1]:mt-3 [&_h1]:mb-1
          [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:text-foreground [&_h2]:mt-3 [&_h2]:mb-1
          [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-foreground [&_h3]:mt-2 [&_h3]:mb-1
          [&_p]:my-1.5 [&_strong]:text-foreground [&_strong]:font-medium
          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1.5
          [&_li]:my-0.5 [&_table]:border-collapse [&_table]:my-2
          [&_th]:border [&_th]:px-2 [&_th]:py-1 [&_th]:text-foreground [&_td]:border [&_td]:px-2 [&_td]:py-1"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{pedigree.description}</ReactMarkdown>
      </div>
    </div>
  )
}
