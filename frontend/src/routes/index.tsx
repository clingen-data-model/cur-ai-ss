import { useState } from 'react'
import { useGeneTable } from '@/hooks/useGeneTable'
import { GeneTable } from '@/components/GeneTable'
import { Spinner } from '@/components/ui/spinner'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Button } from '@/components/ui/button'
import { UploadPaperDialog } from '@/components/UploadPaperDialog'
import { FileX } from 'lucide-react'

export function HomePage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const { rows, isLoading, isError, error } = useGeneTable()

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
            <EmptyMedia variant="icon">
              <FileX className="size-4" />
            </EmptyMedia>
            <EmptyTitle>No papers uploaded</EmptyTitle>
            <EmptyDescription>
              Start by uploading a PDF of a research paper to begin extracting structured curation fields.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent className="flex-row justify-center">
            <Button onClick={() => setDialogOpen(true)}>Upload Paper</Button>
          </EmptyContent>
        </Empty>
        <UploadPaperDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Genes</h1>
        <p className="text-muted-foreground">All genes with papers loaded. Select a gene without papers to upload new data.</p>
      </div>
      <GeneTable rows={rows} />
    </div>
  )
}
