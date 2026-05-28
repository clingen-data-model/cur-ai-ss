import React from 'react'
import { useParams } from '@tanstack/react-router'
import { Collapsible } from '@base-ui/react/collapsible'
import { FolderIcon, FileIcon, ChevronRightIcon } from 'lucide-react'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import { usePaperPatients } from '@/hooks/usePaperPatients'
import type { FamilyNode } from '@/hooks/usePaperPatients'
import { Spinner } from '@/components/ui/spinner'
import { PdfHighlighter, PdfLoader } from 'react-pdf-highlighter'
import * as pdfjs from 'pdfjs-dist'

const API_URL = import.meta.env.VITE_API_URL as string

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`

interface FamilyRowProps {
  node: FamilyNode
}

function FamilyRow({ node }: FamilyRowProps) {
  return (
    <Collapsible.Root defaultOpen={false} className="w-full">
      <Collapsible.Trigger className="flex w-full items-center gap-1 rounded px-2 py-1 text-sm hover:bg-muted cursor-pointer group">
        <ChevronRightIcon className="size-3.5 transition-transform group-data-[state=open]:rotate-90" />
        <FolderIcon className="size-3.5 text-amber-500" />
        <span className="truncate">{node.family.identifier}</span>
        <span className="ml-auto text-xs text-muted-foreground">
          {node.patients.length}
        </span>
      </Collapsible.Trigger>
      <Collapsible.Panel className="pl-5 space-y-1">
        {node.patients.map((patient) => (
          <div
            key={patient.id}
            className="flex items-center gap-1.5 rounded px-2 py-1 text-sm hover:bg-muted"
          >
            <FileIcon className="size-3.5 text-blue-400" />
            <span className="truncate">{patient.identifier}</span>
          </div>
        ))}
      </Collapsible.Panel>
    </Collapsible.Root>
  )
}

export function PatientsPage() {
  const params = useParams({ from: '/papers/$paperId/patients' })
  const paperIdNum = parseInt(params.paperId, 10)
  const { paper, familyNodes, isLoading, isError, error } =
    usePaperPatients(paperIdNum)

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
        <div className="text-red-500">
          Error loading paper: {error?.message ?? 'Unknown error'}
        </div>
      </div>
    )
  }

  const pdfUrl = paper ? `${API_URL}${(paper as any).pdf_url}` : null

  return (
    <div className="h-[calc(100vh-8rem)]">
      <ResizablePanelGroup direction="horizontal" className="h-full rounded-lg border">
        <ResizablePanel defaultSize={33} minSize={20}>
          <div className="h-full overflow-y-auto p-2">
            <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Families &amp; Patients
            </div>
            {familyNodes.length === 0 ? (
              <div className="px-2 text-sm text-muted-foreground">
                No families found.
              </div>
            ) : (
              familyNodes.map((node) => (
                <FamilyRow key={node.family.id} node={node} />
              ))
            )}
          </div>
        </ResizablePanel>

        <ResizableHandle />

        <ResizablePanel defaultSize={67}>
          <div className="h-full overflow-hidden">
            {pdfUrl ? (
              <PdfLoader url={pdfUrl} beforeLoad={<Spinner />}>
                {(pdfDocument) => {
                  const containerRef = React.useRef<HTMLDivElement>(null)
                  return (
                    <div ref={containerRef} style={{ height: '100%', overflow: 'auto' }}>
                      <PdfHighlighter
                        pdfDocument={pdfDocument}
                        scrollRef={() => containerRef}
                        enableAreaSelection={() => false}
                        onScrollChange={() => {}}
                        highlights={[]}
                        onSelectionFinished={() => null}
                        highlightTransform={() => <></>}
                      />
                    </div>
                  )
                }}
              </PdfLoader>
            ) : (
              <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
                No PDF available.
              </div>
            )}
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
