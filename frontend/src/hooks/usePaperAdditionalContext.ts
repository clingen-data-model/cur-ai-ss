import { useQuery } from '@tanstack/react-query'
import { getPaperPapersPaperIdGet } from '@/api/generated'
import type { PaperResp } from '@/api/generated/types.gen'

/** The paper's additional context, for a dialog that shows it in its box
 * before queueing a run. Shares the ['paper', id] cache with the extraction
 * page (usePaperOccurrences), where every such dialog lives, so opening one
 * there reads what is already loaded and sends nothing. `loaded` gates the
 * Confirm button: the box is the whole field, and sending it back before it
 * was filled in would wipe what a curator wrote. */
export function usePaperAdditionalContext(paperId: number, enabled: boolean) {
  const { data, isSuccess } = useQuery({
    queryKey: ['paper', paperId],
    queryFn: () => getPaperPapersPaperIdGet({ path: { paper_id: paperId } }),
    staleTime: 5 * 60 * 1000,
    enabled,
    // The SDK's static return type is the response envelope, but the client
    // is configured with responseStyle: 'data', so at runtime this is the
    // body (see hooks/usePaperOccurrences.ts, which casts the same way).
    select: (resp) => (resp as unknown as PaperResp).paper_global_additional_context ?? '',
  })
  return { context: data, loaded: isSuccess }
}
