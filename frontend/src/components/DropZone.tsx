/* Drag-and-drop file picker, shared by paper upload and avatar upload.
 *
 * Lived inside UploadPaperDialog until the settings page needed the same
 * control. Nothing about it was paper-specific -- `accept` and `hint` were
 * already parameters -- so it moved here unchanged rather than being
 * reimplemented.
 */
import { useRef } from 'react'
import { File as FileIcon, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatFileSize } from '@/lib/utils'

export function DropZone({
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

export function FileCard({ file, onRemove }: { file: File; onRemove: () => void }) {
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
