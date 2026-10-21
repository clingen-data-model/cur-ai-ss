import { useQuery } from '@tanstack/react-query'
import { getPaperPapersPaperIdGet } from '@/api/generated'
import type { PaperResp } from '@/api/generated/types.gen'

/** The paper's context notes, for a dialog that lists them before queueing
 * a run. Shares the ['paper', id] cache with the extraction page
 * (usePaperOccurrences), where every such dialog lives, so opening one
 * there reads what is already loaded and sends nothing. `undefined` until
 * loaded, which the list shows as such. */
export function usePaperContextNotes(paperId: number, enabled: boolean) {
  const { data } = useQuery({
    queryKey: ['paper', paperId],
    queryFn: () => getPaperPapersPaperIdGet({ path: { paper_id: paperId } }),
    staleTime: 5 * 60 * 1000,
    enabled,
    // The SDK's static return type is the response envelope, but the client
    // is configured with responseStyle: 'data', so at runtime this is the
    // body (see hooks/usePaperOccurrences.ts, which casts the same way).
    select: (resp) => (resp as unknown as PaperResp).context_notes ?? [],
  })
  return data
}
