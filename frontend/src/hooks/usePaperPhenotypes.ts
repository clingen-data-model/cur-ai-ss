import { useQuery } from '@tanstack/react-query'
import { getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet } from '@/api/generated'
import type { PhenotypeResp } from '@/api/generated/types.gen'

const STALE_TIME = 5 * 60 * 1000

export function usePaperPhenotypes(
  paperId: number,
  patientIds: number[],
): Record<number, PhenotypeResp[]> {
  const phenotypeQueries = useQuery<Record<number, PhenotypeResp[]>>({
    queryKey: ['phenotypes', paperId, patientIds],
    queryFn: async () => {
      const results: Record<number, PhenotypeResp[]> = {}

      for (const patientId of patientIds) {
        try {
          const phenotypes = await getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet({
            path: { paper_id: paperId, patient_id: patientId },
          })
          results[patientId] = (phenotypes ?? []) as PhenotypeResp[]
        } catch (error) {
          results[patientId] = []
        }
      }

      return results
    },
    staleTime: STALE_TIME,
    enabled: patientIds.length > 0,
    initialData: {},
  })

  return (phenotypeQueries.data ?? {}) as Record<number, PhenotypeResp[]>
}
