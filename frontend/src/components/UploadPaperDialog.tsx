import { useEffect, useRef, useState } from 'react'
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
import { searchGenesGenesSearchGet } from '@/api/generated'
import { uploadPaper } from '@/lib/api'
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { formatFileSize } from '@/lib/utils'

interface UploadPaperDialogProps {
  open: boolean
  setDialogOpen: (open: boolean) => void
  initialGene?: string
}

// nginx caps the request body at `client_max_body_size 200M` (binary MB), and
// Streamlit's uploader has always passed max_upload_size=200. Without a check here
// an oversized file uploads in full before nginx 413s it, which on a slow link means
// minutes of progress bar followed by a failure that says nothing useful.
const MAX_UPLOAD_BYTES = 200 * 1024 * 1024

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

export function UploadPaperDialog({ open, setDialogOpen, initialGene }: UploadPaperDialogProps) {
  const [selectedGene, setSelectedGene] = useState<string>(initialGene ?? '')
  const [genePrefix, setGenePrefix] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const [supplement, setSupplement] = useState<File | null>(null)
  // null until the first progress event, and again whenever the browser cannot
  // size the body -- the bar falls back to indeterminate rather than showing 0%.
  const [percent, setPercent] = useState<number | null>(null)
  const queryClient = useQueryClient()

  // Sync selectedGene whenever the dialog opens (handles the gene-locked case)
  useEffect(() => {
    if (open) setSelectedGene(initialGene ?? '')
  }, [open, initialGene])

  const { data: genesData } = useQuery({
    queryKey: ['genes', 'search', genePrefix],
    queryFn: () => searchGenesGenesSearchGet({ query: { prefix: genePrefix, limit: 1000 } }),
    enabled: !initialGene,
  })
  const genes = Array.isArray(genesData) ? genesData : []

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedGene || !file) {
        throw new Error('Please select a gene and upload file')
      }
      setPercent(0)
      return uploadPaper(
        {
          gene_symbol: selectedGene,
          uploaded_file: file,
          supplement_file: supplement,
        },
        (progress) => setPercent(progress.percent),
      )
    },
    onSuccess: () => {
      setPercent(null)
      toast.success('Paper uploaded successfully')
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      setDialogOpen(false)
      setSelectedGene(initialGene ?? '')
      setGenePrefix('')
      setFile(null)
      setSupplement(null)
    },
    onError: (error) => {
      setPercent(null)
      toast.error(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
    },
  })

  const handleFile = (incoming: File | undefined) => {
    if (!incoming) return
    if (incoming.type !== 'application/pdf') {
      toast.error('Please upload a PDF file.')
      return
    }
    if (oversized(incoming)) return
    setFile(incoming)
  }

  const handleSupplement = (incoming: File | undefined) => {
    if (!incoming) return
    if (!SUPPLEMENT_TYPES.includes(incoming.type)) {
      toast.error('Supplement must be a PDF, DOCX, or XLSX file.')
      return
    }
    if (oversized(incoming)) return
    setSupplement(incoming)
  }

  /** Reject a single file up front; the combined check below catches the rest. */
  const oversized = (candidate: File): boolean => {
    if (candidate.size <= MAX_UPLOAD_BYTES) return false
    toast.error(
      `${candidate.name} is ${formatFileSize(candidate.size)}. The limit is ` +
        `${formatFileSize(MAX_UPLOAD_BYTES)}.`,
    )
    return true
  }

  // Both files travel in one multipart body, so two individually-legal files can
  // still exceed the limit together. Checked at submit rather than on selection,
  // since which file to blame is the user's call, not ours.
  const totalBytes = (file?.size ?? 0) + (supplement?.size ?? 0)
  const overCombinedLimit = totalBytes > MAX_UPLOAD_BYTES

  const resetFile = () => setFile(null)
  const resetSupplement = () => setSupplement(null)

  return (
    <Dialog open={open} onOpenChange={setDialogOpen}>
      <DialogContent>
        <div className="space-y-4">
          {/* Gene selector */}
          <div>
            <label className="text-sm font-medium block mb-1.5">Gene Symbol</label>
            {initialGene ? (
              <div className="flex h-8 items-center rounded-lg border border-input bg-muted px-2.5 text-sm text-muted-foreground">
                {initialGene}
              </div>
            ) : (
              <Combobox value={selectedGene} onValueChange={(val: string | null) => setSelectedGene(val ?? '')} onInputValueChange={(val: string | null) => setGenePrefix(val ?? '')}>
                <ComboboxInput placeholder="Select a gene..." className="w-full" showClear />
                <ComboboxContent>
                  <ComboboxList>
                    {genes.map((g: any) => (
                      <ComboboxItem key={g.symbol} value={g.symbol}>
                        {g.symbol}
                      </ComboboxItem>
                    ))}
                    <ComboboxEmpty>No genes found.</ComboboxEmpty>
                  </ComboboxList>
                </ComboboxContent>
              </Combobox>
            )}
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

          {/* Upload progress — only while in flight. `value={null}` is Base UI's
              indeterminate state, which is what a body the browser cannot size
              leaves us with. */}
          {uploadMutation.isPending && (
            <Progress value={percent}>
              <ProgressLabel>Uploading {file?.name}</ProgressLabel>
              <ProgressValue />
            </Progress>
          )}

          {/* Actions — inline validation hints + cancel/submit */}
          <div className="flex items-center justify-end gap-2">
            {file && !selectedGene && (
              <p className="text-xs text-destructive mr-auto">Please select a gene.</p>
            )}
            {selectedGene && !file && (
              <p className="text-xs text-destructive mr-auto">Please upload a PDF.</p>
            )}
            {overCombinedLimit && (
              <p className="text-xs text-destructive mr-auto">
                Together these files are {formatFileSize(totalBytes)}, over the{' '}
                {formatFileSize(MAX_UPLOAD_BYTES)} limit.
              </p>
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
              disabled={
                uploadMutation.isPending ||
                !selectedGene ||
                !file ||
                overCombinedLimit
              }
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
