import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import {
  getPaperPapersPaperIdGet,
  getFamiliesPapersPaperIdFamiliesGet,
  getPatientsPapersPaperIdPatientsGet,
} from '@/api/generated'
import type { FamilyResp, PatientResp, PaperResp } from '@/api/generated/types.gen'

export type { FamilyResp, PatientResp, PaperResp }

export interface FamilyNode {
  family: FamilyResp
  patients: PatientResp[]
}

const STALE_TIME = 5 * 60 * 1000

export function usePaperPatients(paperId: number) {
  const paperQuery = useQuery({
    queryKey: ['paper', paperId],
    queryFn: () => getPaperPapersPaperIdGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const familiesQuery = useQuery({
    queryKey: ['families', paperId],
    queryFn: () => getFamiliesPapersPaperIdFamiliesGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const patientsQuery = useQuery({
    queryKey: ['patients', paperId],
    queryFn: () => getPatientsPapersPaperIdPatientsGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const familyNodes = useMemo<FamilyNode[]>(() => {
    if (!familiesQuery.data || !patientsQuery.data) return []
    const families = Array.isArray(familiesQuery.data) ? familiesQuery.data : []
    const patients = Array.isArray(patientsQuery.data) ? patientsQuery.data : []
    return families.map((family) => ({
      family,
      patients: patients.filter((p) => p.family_id === family.id),
    }))
  }, [familiesQuery.data, patientsQuery.data])

  return {
    paper: paperQuery.data as PaperResp | undefined,
    familyNodes,
    isLoading:
      paperQuery.isPending || familiesQuery.isPending || patientsQuery.isPending,
    isError:
      paperQuery.isError || familiesQuery.isError || patientsQuery.isError,
    error: paperQuery.error ?? familiesQuery.error ?? patientsQuery.error,
  }
}
