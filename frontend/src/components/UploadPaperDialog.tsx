import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Combobox } from '@/components/ui/combobox'
import { listGenesGenesGet, putPaperPapersPut } from '@/api/generated'
import { Spinner } from '@/components/ui/spinner'

interface UploadPaperDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function UploadPaperDialog({ open, onOpenChange }: UploadPaperDialogProps) {
  const [selectedGene, setSelectedGene] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const queryClient = useQueryClient()

  const { data: genes = [] } = useQuery({
    queryKey: ['genes'],
    queryFn: () => listGenesGenesGet(),
  })

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedGene || !file) {
        throw new Error('Please select a gene and upload file')
      }
      return putPaperPapersPut({
        body: {
          gene_symbol: selectedGene,
          uploaded_file: file,
        },
      })
    },
    onSuccess: () => {
      toast.success('Paper uploaded successfully')
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      onOpenChange(false)
      setSelectedGene('')
      setFile(null)
    },
    onError: (error) => {
      toast.error(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload Paper</DialogTitle>
          <DialogDescription>
            Select a gene and upload a PDF to begin extraction
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium">Gene Symbol</label>
            <Combobox
              options={genes.map(g => ({ label: g.symbol, value: g.symbol }))}
              value={selectedGene}
              onValueChange={setSelectedGene}
              placeholder="Select a gene..."
            />
          </div>

          <div>
            <label className="text-sm font-medium">PDF File</label>
            <Input
              type="file"
              accept=".pdf"
              onChange={(e) => setFile(e.currentTarget.files?.[0] || null)}
            />
          </div>

          <div className="flex gap-2 justify-end">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={uploadMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={uploadMutation.isPending || !selectedGene || !file}
            >
              {uploadMutation.isPending ? (
                <>
                  <Spinner className="mr-2" />
                  Uploading...
                </>
              ) : (
                'Upload'
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
