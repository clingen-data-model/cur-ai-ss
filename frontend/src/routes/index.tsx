import { useState } from 'react'
import { useGeneTable } from '@/hooks/useGeneTable'
import { GeneTable } from '@/components/GeneTable'
import { Spinner } from '@/components/ui/spinner'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { UploadPaperDialog } from '@/components/UploadPaperDialog'
import { FileX, FolderPlus } from 'lucide-react'
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
          <h1 className="text-2xl font-bold">Genes</h1>
          <p className="text-muted-foreground">All genes with uploaded papers.</p>
        </div>
        <Tooltip>
          <TooltipTrigger render={<Button onClick={() => setDialogOpen(true)}><FolderPlus />Upload paper</Button>} />
          <TooltipContent>Upload a paper and select its gene from the list</TooltipContent>
        </Tooltip>
      </div>
      <GeneTable rows={rows} papersByGene={papersByGene} />
      <UploadPaperDialog open={dialogOpen} setDialogOpen={setDialogOpen} />
    </div>
  )
}
