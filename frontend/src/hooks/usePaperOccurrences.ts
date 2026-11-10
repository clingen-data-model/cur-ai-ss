import { useEffect, useMemo, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
import { POLL_WHILE_ACTIVE_MS } from '@/lib/polling'
import { ACTIVE_TASK_STATUSES } from '@/lib/taskState'

export type { PaperResp, PatientResp, VariantResp, PatientVariantOccurrenceResp }

const STALE_TIME = 5 * 60 * 1000

export interface OccurrenceRow {
  occurrence: PatientVariantOccurrenceResp
  patient: PatientResp
  variant: VariantResp
}

export function usePaperOccurrences(paperId: number) {
  const queryClient = useQueryClient()
  const paperQuery = useQuery({
    queryKey: ['paper', paperId],
    queryFn: () => getPaperPapersPaperIdGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
    // The page's status badge and its section gates ("fills in once it
    // completes") are computed from this response's tasks, so while any is
    // in flight the page follows the pipeline at the worker's cadence. Off
    // once the paper is idle: a finished paper has nothing to learn. Without
    // this the badge sat on "running" until the stale time ran out.
    refetchInterval: (query) =>
      query.state.data?.tasks?.some((t) => ACTIVE_TASK_STATUSES.has(t.status))
        ? POLL_WHILE_ACTIVE_MS
        : false,
  })

  // A task that finishes has written its output into some other query of
  // this paper (patients, variants, phenotypes, occurrences, flags...), so
  // when the task set changes state, refresh every query keyed on this paper
  // but this one, which just did. The first load sets the baseline only.
  const taskFingerprint = (paperQuery.data?.tasks ?? [])
    .map((t) => `${t.id}:${t.status}`)
    .join(',')
  const seenFingerprint = useRef<string | null>(null)
  useEffect(() => {
    if (!paperQuery.data) return
    if (seenFingerprint.current === null || seenFingerprint.current === taskFingerprint) {
      seenFingerprint.current = taskFingerprint
      return
    }
    seenFingerprint.current = taskFingerprint
    queryClient.invalidateQueries({
      predicate: (query) => query.queryKey[1] === paperId && query.queryKey[0] !== 'paper',
    })
  }, [taskFingerprint, paperQuery.data, paperId, queryClient])

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

    const result: OccurrenceRow[] = []
    for (const occurrence of occurrences) {
      const patient = patientsById.get(occurrence.patient_id)
      const variant = variantsById.get(occurrence.variant_id)
      if (!patient || !variant) continue

      result.push({ occurrence, patient, variant })
    }

    // Group by patient, and keep a pair's two occurrences adjacent; the
    // Occurrences table then draws each pair as one row (mergePairs there).
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
    allPatients: patientsQuery.data ?? [],
    allVariants: variantsQuery.data ?? [],
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
