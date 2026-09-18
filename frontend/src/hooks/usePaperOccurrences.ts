import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  getPaperPapersPaperIdGet,
  getOccurrencesPapersPaperIdOccurrencesGet,
  getPatientsPapersPaperIdPatientsGet,
  getVariantsPapersPaperIdVariantsGet,
} from '@/api/generated'
import type {
  PaperResp,
  PatientResp,
  VariantResp,
  PatientVariantOccurrenceResp,
} from '@/api/generated/types.gen'

export type { PaperResp, PatientResp, VariantResp, PatientVariantOccurrenceResp }

const STALE_TIME = 5 * 60 * 1000

export interface OccurrenceRow {
  occurrence: PatientVariantOccurrenceResp
  patient: PatientResp
  variant: VariantResp
  /** The other half of a compound-het pair, when this occurrence is paired. */
  pairedVariant: VariantResp | null
}

export function usePaperOccurrences(paperId: number) {
  const paperQuery = useQuery({
    queryKey: ['paper', paperId],
    queryFn: () => getPaperPapersPaperIdGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const occurrencesQuery = useQuery({
    queryKey: ['occurrences', paperId],
    queryFn: () => getOccurrencesPapersPaperIdOccurrencesGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const patientsQuery = useQuery({
    queryKey: ['patients', paperId],
    queryFn: () => getPatientsPapersPaperIdPatientsGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const variantsQuery = useQuery({
    queryKey: ['variants', paperId],
    queryFn: () => getVariantsPapersPaperIdVariantsGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const rows = useMemo<OccurrenceRow[]>(() => {
    const occurrences = occurrencesQuery.data
    const patients = patientsQuery.data
    const variants = variantsQuery.data
    if (!occurrences || !patients || !variants) return []

    const patientsById = new Map(patients.map((p) => [p.id, p]))
    const variantsById = new Map(variants.map((v) => [v.id, v]))
    const occurrencesById = new Map(occurrences.map((o) => [o.id, o]))

    const result: OccurrenceRow[] = []
    for (const occurrence of occurrences) {
      const patient = patientsById.get(occurrence.patient_id)
      const variant = variantsById.get(occurrence.variant_id)
      if (!patient || !variant) continue

      let pairedVariant: VariantResp | null = null
      if (occurrence.paired_variant_link_id != null) {
        const pairedOccurrence = occurrencesById.get(occurrence.paired_variant_link_id)
        if (pairedOccurrence) {
          pairedVariant = variantsById.get(pairedOccurrence.variant_id) ?? null
        }
      }

      result.push({ occurrence, patient, variant, pairedVariant })
    }

    // Group by patient, and keep a pair's two occurrences adjacent -- mirrors
    // the Streamlit Occurrences tab's sort order.
    result.sort((a, b) => {
      if (a.occurrence.patient_id !== b.occurrence.patient_id) {
        return a.occurrence.patient_id - b.occurrence.patient_id
      }
      return (a.occurrence.paired_variant_link_id ?? 0) - (b.occurrence.paired_variant_link_id ?? 0)
    })

    return result
  }, [occurrencesQuery.data, patientsQuery.data, variantsQuery.data])

  // Patients/variants extraction surfaces even when linking hasn't happened
  // (or failed) for them yet, so "no occurrence references this id" is the
  // read of "unassociated" -- not a separate extraction step of its own.
  const unassociatedPatients = useMemo(() => {
    const patients = patientsQuery.data
    const occurrences = occurrencesQuery.data
    if (!patients || !occurrences) return []
    const linkedPatientIds = new Set(occurrences.map((o) => o.patient_id))
    return patients.filter((p) => !linkedPatientIds.has(p.id))
  }, [patientsQuery.data, occurrencesQuery.data])

  const unassociatedVariants = useMemo(() => {
    const variants = variantsQuery.data
    const occurrences = occurrencesQuery.data
    if (!variants || !occurrences) return []
    const linkedVariantIds = new Set(occurrences.map((o) => o.variant_id))
    return variants.filter((v) => !linkedVariantIds.has(v.id))
  }, [variantsQuery.data, occurrencesQuery.data])

  return {
    paper: paperQuery.data as PaperResp | undefined,
    rows,
    unassociatedPatients,
    unassociatedVariants,
    isLoading:
      paperQuery.isPending ||
      occurrencesQuery.isPending ||
      patientsQuery.isPending ||
      variantsQuery.isPending,
    isError:
      paperQuery.isError || occurrencesQuery.isError || patientsQuery.isError || variantsQuery.isError,
    error: paperQuery.error ?? occurrencesQuery.error ?? patientsQuery.error ?? variantsQuery.error,
  }
}
