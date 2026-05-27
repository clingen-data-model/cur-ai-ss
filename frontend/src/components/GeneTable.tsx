import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { GeneRow } from '@/hooks/useGeneTable'

interface GeneTableProps {
  rows: GeneRow[]
}

export function GeneTable({ rows }: GeneTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Gene</TableHead>
          <TableHead className="text-right">Papers</TableHead>
          <TableHead className="text-right">Patients</TableHead>
          <TableHead className="text-right">Variants</TableHead>
          <TableHead className="text-center">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const hasPapers = row.paper_count > 0
          return (
            <TableRow
              key={row.gene_id}
              className={!hasPapers ? 'bg-slate-50' : ''}
            >
              <TableCell className={!hasPapers ? 'text-slate-400 italic' : 'font-medium'}>
                {row.gene_symbol}
              </TableCell>
              <TableCell className="text-right">{hasPapers ? row.paper_count : '—'}</TableCell>
              <TableCell className="text-right">{hasPapers ? row.patient_count : '—'}</TableCell>
              <TableCell className="text-right">{hasPapers ? row.variant_count : '—'}</TableCell>
              <TableCell className="text-center">
                {!hasPapers && (
                  <button
                    type="button"
                    className="text-xs px-2 py-1 rounded border border-slate-300 hover:bg-slate-100"
                  >
                    Upload paper
                  </button>
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
