import { useQuery, useQueries } from '@tanstack/react-query'
import { useMemo } from 'react'
import {
  getFamiliesPapersPaperIdFamiliesGet,
  getPatientsPapersPaperIdPatientsGet,
  getVariantsPapersPaperIdVariantsGet,
  getOccurrencesPapersPaperIdOccurrencesGet,
  getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet,
} from '@/api/generated'
import { buildGraphElements } from '@/lib/graphElements'
import type { ElementDefinition } from 'cytoscape'

const STALE_TIME = 5 * 60 * 1000

export function usePaperGraph(paperId: string | undefined) {
  const papIdNum = paperId ? Number(paperId) : undefined

  // Base queries: families, patients, variants, occurrences
  const familiesQuery = useQuery({
    queryKey: ['families', papIdNum],
    queryFn: () => getFamiliesPapersPaperIdFamiliesGet({ path: { paper_id: papIdNum! } }),
    enabled: !!papIdNum,
    staleTime: STALE_TIME,
  })

  const patientsQuery = useQuery({
    queryKey: ['patients', papIdNum],
    queryFn: () => getPatientsPapersPaperIdPatientsGet({ path: { paper_id: papIdNum! } }),
    enabled: !!papIdNum,
    staleTime: STALE_TIME,
  })

  const variantsQuery = useQuery({
    queryKey: ['variants', papIdNum],
    queryFn: () => getVariantsPapersPaperIdVariantsGet({ path: { paper_id: papIdNum! } }),
    enabled: !!papIdNum,
    staleTime: STALE_TIME,
  })

  const occurrencesQuery = useQuery({
    queryKey: ['occurrences', papIdNum],
    queryFn: () => getOccurrencesPapersPaperIdOccurrencesGet({ path: { paper_id: papIdNum! } }),
    enabled: !!papIdNum,
    staleTime: STALE_TIME,
  })

  // Dependent queries: phenotypes for each patient (parallel once patients load)
  const phenotypeQueries = useQueries({
    queries: (patientsQuery.data ?? []).map((patient) => ({
      queryKey: ['phenotypes', papIdNum, patient.id],
      queryFn: () =>
        getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet({
          path: { paper_id: papIdNum!, patient_id: patient.id },
        }),
      enabled: !!papIdNum && patientsQuery.isSuccess,
      staleTime: STALE_TIME,
    })),
  })

  // Flatten all phenotypes from individual queries
  const allPhenotypesLoaded = phenotypeQueries.every((q) => q.isSuccess)
  const phenotypes = phenotypeQueries.flatMap((q) => q.data ?? [])

  // Build graph elements once all data is ready
  const elements = useMemo<ElementDefinition[]>(() => {
    if (
      !familiesQuery.data ||
      !patientsQuery.data ||
      !variantsQuery.data ||
      !occurrencesQuery.data ||
      !allPhenotypesLoaded
    ) {
      return []
    }

    return buildGraphElements(
      familiesQuery.data,
      patientsQuery.data,
      variantsQuery.data,
      occurrencesQuery.data,
      phenotypes,
    )
  }, [familiesQuery.data, patientsQuery.data, variantsQuery.data, occurrencesQuery.data, allPhenotypesLoaded, phenotypes])

  const isLoading =
    familiesQuery.isPending ||
    patientsQuery.isPending ||
    variantsQuery.isPending ||
    occurrencesQuery.isPending ||
    phenotypeQueries.some((q) => q.isPending)

  const isError =
    familiesQuery.isError || patientsQuery.isError || variantsQuery.isError || occurrencesQuery.isError

  const error = familiesQuery.error || patientsQuery.error || variantsQuery.error || occurrencesQuery.error

  return {
    elements,
    isLoading,
    isError,
    error,
  }
}
