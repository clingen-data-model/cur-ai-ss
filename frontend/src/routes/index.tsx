import { useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useGeneTable } from '@/hooks/useGeneTable'
import { usePapers } from '@/hooks/usePapers'
import { GeneTable } from '@/components/GeneTable'
import { PapersTable } from '@/components/PapersTable'
import { ExtractionStatusFilter } from '@/components/ExtractionStatusFilter'
import { ReviewStatusFilter } from '@/components/ReviewStatusFilter'
import { WorkedByFilter } from '@/components/WorkedByFilter'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Spinner } from '@/components/ui/spinner'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle } from '@/components/ui/alert'
import { UploadPaperDialog } from '@/components/UploadPaperDialog'
import { FileX, FolderPlus, UserRoundSearch } from 'lucide-react'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

export function HomePage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const { rows, papersByGene, isLoading, isError, error } = useGeneTable()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-red-500">Error loading genes: {error?.message || 'Unknown error'}</div>
      </div>
    )
  }

  const hasNoPapers = rows.every(row => row.paper_count === 0)

  if (hasNoPapers) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Empty>
          <EmptyHeader>
            <Alert className="w-fit border-red-200 bg-red-50 text-red-900 text-center justify-center flex flex-col items-center">
              <FileX className="size-4" />
              <AlertTitle>No Papers Uploaded</AlertTitle>
            </Alert>
            <EmptyDescription>
              Start by uploading a PDF of a research paper to begin extracting structured curation fields.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent className="flex-row justify-center">
            <Button onClick={() => setDialogOpen(true)}><FolderPlus />Create a Curation</Button>
          </EmptyContent>
        </Empty>
        <UploadPaperDialog open={dialogOpen} setDialogOpen={setDialogOpen} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Curations</h1>
          <p className="text-muted-foreground">
            Browse every gene, or just the papers you have worked on.
          </p>
        </div>
        <Tooltip>
          <TooltipTrigger render={<Button onClick={() => setDialogOpen(true)}><FolderPlus />Upload paper</Button>} />
          <TooltipContent>Upload a paper and select its gene from the list</TooltipContent>
        </Tooltip>
      </div>

      {/* Tabs rather than routes: two views of the same collection, and the
          switch should not cost a navigation or lose the table's filter. */}
      <Tabs defaultValue="genes">
        <TabsList>
          <TabsTrigger value="genes">Genes</TabsTrigger>
          <TabsTrigger value="papers">All Papers</TabsTrigger>
        </TabsList>
        <TabsContent value="genes" className="mt-4">
          <GeneTable rows={rows} papersByGene={papersByGene} />
        </TabsContent>
        <TabsContent value="papers" className="mt-4">
          <AllPapersTab />
        </TabsContent>
      </Tabs>

      <UploadPaperDialog open={dialogOpen} setDialogOpen={setDialogOpen} />
    </div>
  )
}

/** Split out so its query only runs once the tab is opened, rather than on
 *  every visit to the genes view. */
function AllPapersTab() {
  const search = useSearch({ from: '/' })
  const { worked_by: workedBy = 'anyone', status, review_status } = search
  const navigate = useNavigate({ from: '/' })
  const { papers, people, total, beforeStatus, isLoading, isRefreshing, isError, error } =
    usePapers(workedBy, status, review_status)

  const filtered = workedBy !== 'anyone' || status !== undefined
  // Preserve the other filter when changing one -- they compose.
  const withSearch = (next: Partial<typeof search>) => {
    const merged = { ...search, ...next }
    return Object.fromEntries(
      Object.entries(merged).filter(([, v]) => v !== undefined && v !== 'anyone'),
    )
  }

  // The header renders unconditionally, above every branch below. Returning
  // early on a loading state used to take the filter down with the table, so
  // choosing a person made the control that had just been clicked disappear and
  // come back -- and only the first time each person was picked, since a second
  // visit was served from cache.
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {isLoading
            ? '\u00a0'
            : filtered
              ? `${papers.length} of ${beforeStatus && status ? beforeStatus : (total ?? papers.length)} papers`
              : `${papers.length} papers`}
          {/* A quiet hint rather than a spinner: the rows on screen are the
              previous scope's and still readable while the new ones load. */}
          {isRefreshing && <span className="ml-2 opacity-60">updating…</span>}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <ExtractionStatusFilter
            value={status}
            onChange={(next) =>
              navigate({ search: withSearch({ status: next }), replace: true })
            }
          />
          <ReviewStatusFilter
            value={review_status}
            onChange={(next) =>
              navigate({ search: withSearch({ review_status: next }), replace: true })
            }
          />
          <WorkedByFilter
            value={workedBy}
            people={people}
            onChange={(next) =>
              navigate({ search: withSearch({ worked_by: next }), replace: true })
            }
          />
        </div>
      </div>

      <div
        // Only the rows dim while a new scope loads, so the page does not jump.
        className={isRefreshing ? 'opacity-60 transition-opacity' : undefined}
      >
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : isError ? (
          <div className="py-12 text-center text-red-500">
            Error loading papers: {error?.message || 'Unknown error'}
          </div>
        ) : papers.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <UserRoundSearch />
              </EmptyMedia>
              <EmptyTitle>No papers match that filter</EmptyTitle>
              <EmptyDescription>
                Papers are listed here once someone uploads one, runs an agent on
                it, or edits its extracted data.
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent className="flex-row justify-center">
              <Button
                variant="outline"
                onClick={() => navigate({ search: {}, replace: true })}
              >
                Show all papers
              </Button>
            </EmptyContent>
          </Empty>
        ) : (
          <PapersTable papers={papers} />
        )}
      </div>
    </div>
  )
}
