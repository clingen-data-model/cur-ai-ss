import React, { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { ChevronDown, ChevronRight, FolderPlus } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { listTasksPapersPaperIdTasksGet } from '@/api/generated'
import { DataTable } from '@/components/ui/data-table'
import { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext, CarouselCounter } from '@/components/ui/carousel'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { UploadPaperDialog } from '@/components/UploadPaperDialog'
import { TaskDAG } from '@/components/TaskDAG'
import { STATUS_BADGE } from '@/components/StatusBadge'
import { DeletePaperButton, RerunTaskButton } from '@/components/PaperActions'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import type { GeneRow, PaperSummaryResp } from '@/hooks/useGeneTable'
import type { PaperTag } from '@/api/generated/types.gen'
import { API_BASE_URL } from '@/lib/api'



const TAG_COLORS: Record<PaperTag, string> = {
  'TrainingSet': 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  'ValidationSet': 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300',
  'FailedPaperRelevancy': 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
}



function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}


/** Fetches a paper's tasks on demand, so the list response need not carry them.
 *
 * GET /papers returns one summarised `status` per paper rather than its task
 * list -- embedding them measured at 90.5% of that response. The full list is
 * only needed by the DAG, which lives behind a dialog, so it is fetched when
 * that dialog opens and cached per paper thereafter.
 */
function PaperTaskDAG({ paperId, enabled }: { paperId: number; enabled: boolean }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ['paper-tasks', paperId],
    queryFn: () => listTasksPapersPaperIdTasksGet({ path: { paper_id: paperId }, throwOnError: true }),
    enabled,
  })

  if (isPending) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-destructive">
        Could not load pipeline tasks.
      </div>
    )
  }
  return <TaskDAG tasks={data?.data ?? []} />
}

function PaperCard({ paper }: { paper: PaperSummaryResp }) {
  const status = STATUS_BADGE[paper.status]
  const thumbnailSrc = `${API_BASE_URL}${paper.thumbnail_url}`
  const [dagOpen, setDagOpen] = useState(false)

  return (
    <>
      <Card size="sm">
        <div className="flex items-start px-2 pt-2 gap-2">
          {paper.tags && paper.tags.length > 0 && (
            <div className="flex flex-col gap-1">
              {paper.tags.map((tag) => (
                <Badge key={tag} className={`text-xs py-0.5 px-1.5 whitespace-nowrap ${TAG_COLORS[tag as PaperTag] ?? 'bg-gray-50 text-gray-700 dark:bg-gray-950 dark:text-gray-300'}`}>
                  {tag}
                </Badge>
              ))}
            </div>
          )}
          <div className="flex gap-1 ml-auto">
            <RerunTaskButton paper={paper} />
            <DeletePaperButton paper={paper} />
          </div>
        </div>
        <div className="flex justify-center px-3">
          <div className="w-4/5 overflow-hidden rounded-md border border-border shadow-sm">
            <img
              src={thumbnailSrc}
              alt=""
              className="w-full aspect-[3/4] object-cover object-top bg-slate-100"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          </div>
        </div>
        <CardContent className="grid grid-cols-2 gap-x-3 gap-y-2 pt-3">
          <div className="col-span-2 space-y-0.5 min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Title</div>
            <div className="text-xs truncate">
              {paper.title ? (
                <Link
                  to="/papers/$paperId/patients"
                  params={{ paperId: String(paper.id) }}
                  className="text-link hover:underline"
                >
                  {paper.title}
                </Link>
              ) : '—'}
            </div>
          </div>
          <div className="col-span-2 space-y-0.5 min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">First Author</div>
            <div className="text-xs truncate">
              {paper.first_author ? (
                <Link
                  to="/papers/$paperId/patients"
                  params={{ paperId: String(paper.id) }}
                  className="text-link hover:underline"
                >
                  {paper.first_author}
                </Link>
              ) : '—'}
            </div>
          </div>
          <div className="col-span-2 space-y-0.5 min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Filename</div>
            <div className="text-xs truncate">{paper.filename}</div>
          </div>
          {([
            ['Patients', paper.patient_count ?? '—'],
            ['Variants', paper.variant_count ?? '—'],
            ['Occurrences', paper.patient_variant_occurrences_count ?? '—'],
            ['Status', (
              <Tooltip>
                <TooltipTrigger type="button" onClick={() => setDagOpen(true)} className="cursor-pointer">
                  <Badge variant={status.variant} className={`${status.className} hover:opacity-80 transition-opacity`}>
                    {status.label}
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>View pipeline</TooltipContent>
              </Tooltip>
            )],
            ['Modified', formatDate(paper.updated_at)],
          ] as [string, React.ReactNode][]).map(([label, value]) => (
            <div key={label} className="space-y-0.5 min-w-0">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
              <div className="text-xs">{value}</div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Dialog open={dagOpen} onOpenChange={setDagOpen}>
        <DialogContent className="!w-[32vw] !max-w-none h-[90vh]">
          <div className="flex flex-col h-full">
            <div className="border-b pb-4">
              <h2 className="text-lg font-semibold">{paper.title ?? paper.filename}</h2>
              <p className="text-sm text-muted-foreground">Pipeline execution</p>
            </div>
            <div className="flex-1 min-h-0 mt-4">
              <PaperTaskDAG paperId={paper.id} enabled={dagOpen} />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function PaperCarousel({
  papers,
  geneSymbol,
}: {
  papers: PaperSummaryResp[]
  geneSymbol: string
}) {
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    const q = filter.toLowerCase()
    return q
      ? papers.filter(p =>
          p.title?.toLowerCase().includes(q) ||
          p.first_author?.toLowerCase().includes(q) ||
          p.journal_name?.toLowerCase().includes(q),
        )
      : papers
  }, [papers, filter])

  return (
    <div className="px-6 py-3 bg-slate-50 border-t space-y-2">
      {papers.length > 5 && (
        <Input
          placeholder="Search papers..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-sm"
        />
      )}
      {filtered.length === 0 ? (
        <div className="flex h-16 items-center justify-center text-sm text-muted-foreground">
          No results.
        </div>
      ) : (
        <Carousel key={filter} aria-label={`Papers for ${geneSymbol}`}>
          <CarouselContent className={filtered.length <= 2 ? '-ml-1 justify-center' : '-ml-1'}>
            {filtered.map((p) => (
              <CarouselItem key={p.id} className="pl-1 basis-1/3">
                <div className="p-1">
                  <PaperCard paper={p} />
                </div>
              </CarouselItem>
            ))}
          </CarouselContent>
          <div className="flex items-center justify-between mt-2">
            <CarouselCounter />
            <div className="flex gap-2">
              <CarouselPrevious />
              <CarouselNext />
            </div>
          </div>
        </Carousel>
      )}
    </div>
  )
}

interface GeneTableProps {
  rows: GeneRow[]
  papersByGene: Map<string, PaperSummaryResp[]>
}

export function GeneTable({ rows, papersByGene }: GeneTableProps) {
  const [uploadGene, setUploadGene] = useState<string | null>(null)

  const columns: ColumnDef<GeneRow>[] = [
    {
      id: 'expander',
      size: 40,
      enableSorting: false,
      header: () => null,
      cell: ({ row }) => (
        <button type="button" onClick={row.getToggleExpandedHandler()} className="cursor-pointer flex items-center">
          {row.getIsExpanded() ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </button>
      ),
    },
    {
      accessorKey: 'gene_symbol',
      header: 'Gene',
      cell: ({ getValue }) => <span className="font-medium">{getValue() as string}</span>,
    },
    { accessorKey: 'paper_count', header: 'Papers' },
    { accessorKey: 'patient_count', header: 'Patients' },
    { accessorKey: 'variant_count', header: 'Variants' },
    { accessorKey: 'occurrences_count', header: 'Occurrences' },
    {
      id: 'action',
      size: 60,
      enableSorting: false,
      header: () => null,
      cell: ({ row }) => (
        <Tooltip>
          <TooltipTrigger
            type="button"
            className="flex items-center justify-center size-6 rounded border border-slate-300 hover:bg-slate-100 cursor-pointer"
            onClick={() => setUploadGene(row.original.gene_symbol)}
          >
            <FolderPlus className="size-3.5" />
          </TooltipTrigger>
          <TooltipContent>Add paper for {row.original.gene_symbol}</TooltipContent>
        </Tooltip>
      ),
    },
  ]

  return (
    <>
      <DataTable
        columns={columns}
        data={rows}
        filterPlaceholder="Filter genes..."
        getRowCanExpand={() => true}
        renderSubComponent={({ row }) => (
          <PaperCarousel
            papers={papersByGene.get(row.gene_symbol) ?? []}
            geneSymbol={row.gene_symbol}
          />
        )}
      />
      <UploadPaperDialog
        open={uploadGene !== null}
        setDialogOpen={(open) => { if (!open) setUploadGene(null) }}
        initialGene={uploadGene ?? undefined}
      />
    </>
  )
}
