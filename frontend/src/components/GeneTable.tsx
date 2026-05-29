import React, { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { ChevronDown, ChevronRight, FolderPlus, RefreshCw, Trash2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { toast } from 'sonner'
import { deletePaperPapersPaperIdDelete, createTaskPapersPaperIdTasksPost } from '@/api/generated'
import { DataTable } from '@/components/ui/data-table'
import { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext, CarouselCounter } from '@/components/ui/carousel'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogMedia, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { UploadPaperDialog } from '@/components/UploadPaperDialog'
import { TaskDAG, computeStatus, type NodeStatus } from '@/components/TaskDAG'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import type { GeneRow, PaperResp, TaskType } from '@/hooks/useGeneTable'
import type { PaperTag } from '@/api/generated/types.gen'
import type { badgeVariants } from '@/components/ui/badge'
import type { VariantProps } from 'class-variance-authority'

const API_URL = import.meta.env.VITE_API_URL as string

type BadgeVariant = VariantProps<typeof badgeVariants>['variant']

const TAG_COLORS: Record<PaperTag, string> = {
  'TrainingSet': 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  'ValidationSet': 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300',
  'FailedPaperRelevancy': 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
}

const STATUS_BADGE: Record<NodeStatus, { label: string; variant: BadgeVariant; className?: string }> = {
  idle:      { label: 'Not started', variant: 'secondary' },
  pending:   { label: 'Pending',     variant: 'secondary' },
  running:   { label: 'Running',     variant: 'default' },
  partial:   { label: 'In progress', variant: 'outline', className: 'border-amber-500 text-amber-600' },
  completed: { label: 'Done',        variant: 'outline', className: 'border-green-500 text-green-600' },
  failed:    { label: 'Failed',      variant: 'destructive' },
}

const RERUNNABLE_TASK_TYPES: TaskType[] = [
  'PDF Parsing', 'Paper Classifier', 'Paper Metadata',
  'Variant Extraction', 'Pedigree Description', 'Patient Extraction',
  'Segregation Evidence Extraction', 'Segregation Analysis Computed',
  'Variant Harmonization', 'Variant Annotation', 'Patient Variant Occurrences',
  'Phenotype Extraction', 'HPO Linking',
]

function RerunTaskButton({ paper }: { paper: PaperResp }) {
  const [open, setOpen] = useState(false)
  const [taskType, setTaskType] = useState<TaskType>('PDF Parsing')
  const [skipSuccessors, setSkipSuccessors] = useState(false)
  const [context, setContext] = useState('')
  const isRunning = paper.tasks?.some(t => t.status === 'Running' || t.status === 'Queued')

  const mutation = useMutation({
    mutationFn: () => createTaskPapersPaperIdTasksPost({
      path: { paper_id: paper.id },
      body: { type: taskType, skip_successors: skipSuccessors, additional_context: context || null },
      throwOnError: true,
    }),
    onSuccess: () => {
      toast.success('Task queued')
      setOpen(false)
      setContext('')
      setSkipSuccessors(false)
    },
    onError: () => toast.error('Failed to queue task'),
  })

  return (
    <>
      <button
        type="button"
        disabled={!!isRunning}
        onClick={() => setOpen(true)}
        className="flex items-center justify-center size-7 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <RefreshCw className="size-4" />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold">Rerun Agent</h2>
              <p className="text-sm text-muted-foreground mt-0.5">{paper.title ?? paper.filename}</p>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Task</label>
              <Select value={taskType} onValueChange={(v) => setTaskType(v as TaskType)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-40">
                  {RERUNNABLE_TASK_TYPES.map(t => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">
                Additional context <span className="text-muted-foreground font-normal">(optional)</span>
              </label>
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="Any specific instructions for this task run..."
                rows={3}
                className="w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none resize-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                checked={skipSuccessors}
                onChange={(e) => setSkipSuccessors(e.target.checked)}
                className="cursor-pointer"
              />
              Skip successor tasks
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
                {mutation.isPending ? 'Queuing...' : 'Confirm Rerun'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function DeletePaperButton({ paper }: { paper: PaperResp }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => deletePaperPapersPaperIdDelete({ path: { paper_id: paper.id }, throwOnError: true }),
    onSuccess: () => {
      toast.success(`"${paper.title ?? paper.filename}" deleted`)
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: () => toast.error('Failed to delete paper'),
  })

  return (
    <AlertDialog>
      <AlertDialogTrigger
        type="button"
        className="flex items-center justify-center size-7 rounded text-destructive hover:bg-destructive/10 cursor-pointer transition-colors"
      >
        <Trash2 className="size-4" />
      </AlertDialogTrigger>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-destructive/10 text-destructive dark:bg-destructive/20">
            <Trash2 />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete paper?</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete <span className="font-medium text-foreground">{paper.title ?? paper.filename}</span> and all extracted data. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel variant="outline">Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => mutation.mutate()}>Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function PaperCard({ paper }: { paper: PaperResp }) {
  const status = STATUS_BADGE[computeStatus(paper.tasks ?? [])]
  const thumbnailSrc = `${API_URL}${paper.thumbnail_url}`
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
                  className="text-blue-600 hover:underline"
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
                  className="text-blue-600 hover:underline"
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
                <TooltipTrigger render={
                  <button type="button" onClick={() => setDagOpen(true)} className="cursor-pointer">
                    <Badge variant={status.variant} className={`${status.className} hover:opacity-80 transition-opacity`}>
                      {status.label}
                    </Badge>
                  </button>
                } />
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

      <Sheet open={dagOpen} onOpenChange={setDagOpen}>
        <SheetContent side="right" className="w-[680px] sm:max-w-none flex flex-col p-0">
          <SheetHeader className="px-5 pt-5 pb-3 border-b">
            <SheetTitle className="text-sm font-semibold truncate">
              {paper.title ?? paper.filename}
            </SheetTitle>
            <p className="text-xs text-muted-foreground">Pipeline execution</p>
          </SheetHeader>
          <div className="flex-1 min-h-0">
            <TaskDAG tasks={paper.tasks ?? []} />
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}

function PaperCarousel({ papers }: { papers: PaperResp[] }) {
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
        <Carousel key={filter}>
          <CarouselContent className={filtered.length === 2 ? '-ml-1 justify-center' : '-ml-1'}>
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
  papersByGene: Map<string, PaperResp[]>
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
          <PaperCarousel papers={papersByGene.get(row.gene_symbol) ?? []} />
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
