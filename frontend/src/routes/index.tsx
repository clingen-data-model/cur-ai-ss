import { useState } from 'react'
import { useGeneTable } from '@/hooks/useGeneTable'
import { useMyPapers } from '@/hooks/useMyPapers'
import { GeneTable } from '@/components/GeneTable'
import { PapersTable } from '@/components/PapersTable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Spinner } from '@/components/ui/spinner'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
          <TabsTrigger value="mine">My papers</TabsTrigger>
        </TabsList>
        <TabsContent value="genes" className="mt-4">
          <GeneTable rows={rows} papersByGene={papersByGene} />
        </TabsContent>
        <TabsContent value="mine" className="mt-4">
          <MyPapersTab />
        </TabsContent>
      </Tabs>

      <UploadPaperDialog open={dialogOpen} setDialogOpen={setDialogOpen} />
    </div>
  )
}

/** Split out so its query only runs once the tab is opened, rather than on
 *  every visit to the genes view. */
function MyPapersTab() {
  const { papers, isLoading, isError, error } = useMyPapers()

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="py-12 text-center text-red-500">
        Error loading your papers: {error?.message || 'Unknown error'}
      </div>
    )
  }
  if (papers.length === 0) {
    // The common case for a new account, and for most papers: two thirds of
    // them on dev have no recorded human toucher at all.
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <UserRoundSearch />
          </EmptyMedia>
          <EmptyTitle>Nothing here yet</EmptyTitle>
          <EmptyDescription>
            Papers appear here once you upload one, run an agent on it, or edit
            its extracted data.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return <PapersTable papers={papers} />
}
