/* Curator flags for one paper (lib/models/flag.py): decisions an agent made
 * that a curator should look at, each linked to the rows it concerns.
 *
 * One query for the paper, indexed by entity so every table can mark its
 * rows without a request of its own. A flag carries every row it is about
 * (a flag about a patient's phenotype has both ids), so it appears under
 * each of them. Resolution is one-way (see FlagResolveRequest): the
 * mutation posts a note and the server refuses a second resolve.
 */
import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { listFlagsPapersPaperIdFlagsGet, resolveFlagPapersPaperIdFlagsFlagIdResolvePost } from '@/api/generated'
import type { FlagResp } from '@/api/generated/types.gen'
import { apiErrorMessage } from '@/lib/apiError'

export type { FlagResp }

const STALE_TIME = 5 * 60 * 1000

export function isOpen(flag: FlagResp): boolean {
  return flag.resolved_at == null
}

function groupBy(flags: FlagResp[], key: (flag: FlagResp) => number | null | undefined): Map<number, FlagResp[]> {
  const groups = new Map<number, FlagResp[]>()
  for (const flag of flags) {
    const id = key(flag)
    if (id == null) continue
    groups.set(id, [...(groups.get(id) ?? []), flag])
  }
  return groups
}

export interface FlagIndex {
  all: FlagResp[]
  open: FlagResp[]
  byFamily: Map<number, FlagResp[]>
  byPatient: Map<number, FlagResp[]>
  byVariant: Map<number, FlagResp[]>
  byPhenotype: Map<number, FlagResp[]>
  byOccurrence: Map<number, FlagResp[]>
  /** Flags about nothing extracted: no row to sit on, so only the Flags tab shows them. */
  unlinked: FlagResp[]
}

const EMPTY: FlagIndex = {
  all: [],
  open: [],
  byFamily: new Map(),
  byPatient: new Map(),
  byVariant: new Map(),
  byPhenotype: new Map(),
  byOccurrence: new Map(),
  unlinked: [],
}

export function usePaperFlags(paperId: number) {
  const query = useQuery({
    queryKey: ['flags', paperId],
    queryFn: () => listFlagsPapersPaperIdFlagsGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const index = useMemo<FlagIndex>(() => {
    const all = query.data
    if (!all) return EMPTY
    return {
      all,
      open: all.filter(isOpen),
      byFamily: groupBy(all, (f) => f.family_id),
      byPatient: groupBy(all, (f) => f.patient_id),
      byVariant: groupBy(all, (f) => f.variant_id),
      byPhenotype: groupBy(all, (f) => f.phenotype_id),
      byOccurrence: groupBy(all, (f) => f.occurrence_id),
      unlinked: all.filter(
        (f) =>
          f.family_id == null &&
          f.patient_id == null &&
          f.variant_id == null &&
          f.phenotype_id == null &&
          f.occurrence_id == null,
      ),
    }
  }, [query.data])

  return { ...index, isLoading: query.isPending, isError: query.isError, error: query.error }
}

export function useResolveFlag(paperId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ flagId, note }: { flagId: number; note: string }) =>
      resolveFlagPapersPaperIdFlagsFlagIdResolvePost({
        path: { paper_id: paperId, flag_id: flagId },
        body: { note },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['flags', paperId] })
      // The dashboard's open-flag count.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Flag resolved')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to resolve flag')),
  })
}
