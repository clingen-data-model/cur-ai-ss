import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { listPapersPapersGet, listGenesGenesGet } from '@/api/generated'

const STALE_TIME = 5 * 60 * 1000

export interface GeneRow {
  gene_id: number
  gene_symbol: string
  paper_count: number
  patient_count: number
  variant_count: number
}

export function useGeneTable() {
  const papersQuery = useQuery({
    queryKey: ['papers'],
    queryFn: () => listPapersPapersGet({}),
    staleTime: STALE_TIME,
  })

  const genesQuery = useQuery({
    queryKey: ['genes'],
    queryFn: () => listGenesGenesGet({ query: { limit: 1000 } }),
    staleTime: STALE_TIME,
  })

  const rows = useMemo(() => {
    if (!papersQuery.data || !genesQuery.data) return []

    // Aggregate papers by gene_symbol
    const geneStats = new Map<string, { gene_id: number; paper_count: number; patient_count: number; variant_count: number }>()

    for (const paper of papersQuery.data) {
      const key = paper.gene_symbol
      if (!geneStats.has(key)) {
        geneStats.set(key, {
          gene_id: 0, // will be filled from genesQuery
          paper_count: 0,
          patient_count: 0,
          variant_count: 0,
        })
      }
      const stats = geneStats.get(key)!
      stats.paper_count += 1
      stats.patient_count += paper.patient_count || 0
      stats.variant_count += paper.variant_count || 0
    }

    // Build final rows from all genes, filling in stats where available
    const rows: GeneRow[] = genesQuery.data.map((gene) => {
      const stats = geneStats.get(gene.symbol) || {
        gene_id: gene.id,
        paper_count: 0,
        patient_count: 0,
        variant_count: 0,
      }
      return {
        gene_id: gene.id,
        gene_symbol: gene.symbol,
        paper_count: stats.paper_count,
        patient_count: stats.patient_count,
        variant_count: stats.variant_count,
      }
    })

    // Sort: genes with papers first (by paper count desc), then paper-less genes alphabetically
    return rows.sort((a, b) => {
      if (a.paper_count > 0 && b.paper_count === 0) return -1
      if (a.paper_count === 0 && b.paper_count > 0) return 1
      if (a.paper_count > 0 && b.paper_count > 0) return b.paper_count - a.paper_count
      return a.gene_symbol.localeCompare(b.gene_symbol)
    })
  }, [papersQuery.data, genesQuery.data])

  return {
    rows,
    isLoading: papersQuery.isPending || genesQuery.isPending,
    isError: papersQuery.isError || genesQuery.isError,
    error: papersQuery.error || genesQuery.error,
  }
}
