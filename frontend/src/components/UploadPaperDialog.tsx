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

const SUPPLEMENT_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
]

function DropZone({
  accept,
  hint,
  onFile,
  padding = 'py-10',
}: {
  accept: string
  hint: string
  onFile: (file: File | undefined) => void
  padding?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div
      className={`flex justify-center rounded-md border border-dashed border-input px-6 ${padding} cursor-pointer`}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]) }}
      onClick={() => inputRef.current?.click()}
    >
      <div className="text-center">
        <FileIcon className="mx-auto h-7 w-7 text-muted-foreground" aria-hidden />
        <p className="mt-2 text-sm text-muted-foreground">
          Drag and drop or <span className="font-medium text-primary hover:underline underline-offset-4">choose file</span>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = '' }}
      />
    </div>
  )
}

function FileCard({ file, onRemove }: { file: File; onRemove: () => void }) {
  return (
    <div className="relative flex items-center gap-3 rounded-lg border bg-muted px-3 py-2.5">
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
        onClick={onRemove}
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}

export function UploadPaperDialog({ open, setDialogOpen }: UploadPaperDialogProps) {
  const [selectedGene, setSelectedGene] = useState<string>('')
  const [genePrefix, setGenePrefix] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const [supplement, setSupplement] = useState<File | null>(null)
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
          ...(supplement ? { supplement_file: supplement } : {}),
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
      setSupplement(null)
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

  const handleSupplement = (incoming: File | undefined) => {
    if (!incoming) return
    if (!SUPPLEMENT_TYPES.includes(incoming.type)) {
      toast.error('Supplement must be a PDF, DOCX, or XLSX file.')
      return
    }
    setSupplement(incoming)
  }

  const resetFile = () => setFile(null)
  const resetSupplement = () => setSupplement(null)

  return (
    <Dialog open={open} onOpenChange={setDialogOpen}>
      <DialogContent>
        <div className="space-y-4">
          {/* Gene selector */}
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

          {/* Main PDF — drop zone until selected, then file card */}
          <div>
            <label className="text-sm font-medium block mb-1.5">PDF File</label>
            {!file && <DropZone accept=".pdf" hint="PDF only" onFile={handleFile} />}
            {file && <FileCard file={file} onRemove={resetFile} />}
          </div>

          {/* Supplement — only shown after main PDF is selected */}
          {file && (
            <div>
              <label className="text-sm font-medium block mb-1.5">
                Supplement <span className="text-muted-foreground font-normal">(optional)</span>
              </label>
              {!supplement ? (
                <DropZone accept=".pdf,.docx,.xlsx" hint="PDF, DOCX, or XLSX" onFile={handleSupplement} padding="py-8" />
              ) : (
                <FileCard file={supplement} onRemove={resetSupplement} />
              )}
            </div>
          )}

          {/* Actions — inline validation hints + cancel/submit */}
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
