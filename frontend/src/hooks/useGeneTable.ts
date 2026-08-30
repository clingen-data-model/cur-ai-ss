import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { listPapersPapersGet } from '@/api/generated'
import type { PaperResp, TaskType } from '@/api/generated/types.gen'

export type { PaperResp, TaskType }

const STALE_TIME = 5 * 60 * 1000

export interface GeneRow {
  gene_id: number
  gene_symbol: string
  paper_count: number
  patient_count: number
  variant_count: number
  occurrences_count: number
}

export function useGeneTable() {
  const papersQuery = useQuery({
    queryKey: ['papers'],
    queryFn: () => listPapersPapersGet({}),
    staleTime: STALE_TIME,
  })

  const { rows, papersByGene } = useMemo(() => {
    if (!papersQuery.data) return { rows: [], papersByGene: new Map<string, PaperResp[]>() }

    const papers = Array.isArray(papersQuery.data) ? papersQuery.data : []

    const papersByGene = new Map<string, PaperResp[]>()
    const geneStats = new Map<string, { paper_count: number; patient_count: number; variant_count: number; occurrences_count: number }>()

    for (const paper of papers) {
      const key = paper.gene_symbol
      if (!geneStats.has(key)) {
        geneStats.set(key, { paper_count: 0, patient_count: 0, variant_count: 0, occurrences_count: 0 })
        papersByGene.set(key, [])
      }
      const stats = geneStats.get(key)!
      stats.paper_count += 1
      stats.patient_count += paper.patient_count || 0
      stats.variant_count += paper.variant_count || 0
      stats.occurrences_count += paper.patient_variant_occurrences_count || 0
      papersByGene.get(key)!.push(paper)
    }

    const rows: GeneRow[] = Array.from(geneStats.entries()).map(([symbol, stats], index) => ({
      gene_id: index,
      gene_symbol: symbol,
      paper_count: stats.paper_count,
      patient_count: stats.patient_count,
      variant_count: stats.variant_count,
      occurrences_count: stats.occurrences_count,
    }))

    rows.sort((a, b) => b.paper_count - a.paper_count)
    return { rows, papersByGene }
  }, [papersQuery.data])

  return {
    rows,
    papersByGene,
    isLoading: papersQuery.isPending,
    isError: papersQuery.isError,
    error: papersQuery.error,
  }
}
