import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { File as FileIcon, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '@/components/ui/combobox'
import { searchGenesGenesSearchGet, putPaperPapersPut } from '@/api/generated'
import { Spinner } from '@/components/ui/spinner'
import { formatFileSize } from '@/lib/utils'

interface UploadPaperDialogProps {
  open: boolean
  setDialogOpen: (open: boolean) => void
}

export function UploadPaperDialog({ open, setDialogOpen }: UploadPaperDialogProps) {
  const [selectedGene, setSelectedGene] = useState<string>('')
  const [genePrefix, setGenePrefix] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: genes = [] } = useQuery({
    queryKey: ['genes', 'search', genePrefix],
    queryFn: () => searchGenesGenesSearchGet({ query: { prefix: genePrefix, limit: 1000 } }),
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
        throwOnError: true,
      })
    },
    onSuccess: () => {
      toast.success('Paper uploaded successfully')
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      setDialogOpen(false)
      setSelectedGene('')
      setGenePrefix('')
      setFile(null)
    },
    onError: (error) => {
      toast.error(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
    },
  })

  const handleFile = (incoming: File | undefined) => {
    if (!incoming) return
    if (incoming.type !== 'application/pdf') {
      toast.error('Please upload a PDF file.')
      return
    }
    setFile(incoming)
  }

  const resetFile = () => {
    setFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <Dialog open={open} onOpenChange={setDialogOpen}>
      <DialogContent>
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium block mb-1.5">Gene Symbol</label>
            <Combobox value={selectedGene} onValueChange={setSelectedGene} onInputValueChange={setGenePrefix}>
              <ComboboxInput placeholder="Select a gene..." className="w-full" showClear />
              <ComboboxContent>
                <ComboboxList>
                  {genes.map((g) => (
                    <ComboboxItem key={g.symbol} value={g.symbol}>
                      {g.symbol}
                    </ComboboxItem>
                  ))}
                  <ComboboxEmpty>No genes found.</ComboboxEmpty>
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1.5">PDF File</label>
            <div
              className="flex justify-center rounded-md border border-dashed border-input px-6 py-10 cursor-pointer"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                handleFile(e.dataTransfer.files?.[0])
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="text-center">
                <FileIcon className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden />
                <p className="mt-2 text-sm text-muted-foreground">
                  Drag and drop or <span className="font-medium text-primary hover:underline underline-offset-4">choose file</span> to upload
                </p>
                <p className="mt-1 text-xs text-muted-foreground">PDF only</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="sr-only"
                onChange={(e) => {
                  handleFile(e.target.files?.[0])
                  e.target.value = ''
                }}
              />
            </div>

            {file && (
              <div className="relative mt-3 flex items-center gap-3 rounded-lg border bg-muted px-3 py-2.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-background ring-1 ring-inset ring-border">
                  <FileIcon className="h-4 w-4 text-foreground" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-foreground">{file.name}</p>
                  <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground hover:text-foreground"
                  onClick={resetFile}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-2">
            {file && !selectedGene && (
              <p className="text-xs text-destructive mr-auto">Please select a gene.</p>
            )}
            {selectedGene && !file && (
              <p className="text-xs text-destructive mr-auto">Please upload a PDF.</p>
            )}
            <Button
              variant="outline"
              onClick={() => setDialogOpen(false)}
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
