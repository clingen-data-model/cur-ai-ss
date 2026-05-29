import React, { useRef, useState, useEffect } from 'react'
import { useParams } from '@tanstack/react-router'
import { Collapsible } from '@base-ui/react/collapsible'
import { HomeIcon, UserCircleIcon, ChevronRightIcon } from 'lucide-react'
import { usePaperPatients } from '@/hooks/usePaperPatients'
import type { FamilyNode, PatientResp } from '@/hooks/usePaperPatients'
import { Spinner } from '@/components/ui/spinner'
import { TwoColumnWithBottomRightPdf, annotationsToHighlights, type Highlight, type PdfViewerRef } from '@/components/TwoColumnWithBottomRightPdf'
import { PatientDetails, type HighlightArgs } from '@/components/PatientDetails'
import { grobidAnnotationPapersPaperIdGrobidAnnotationPost } from '@/api/generated'
import * as pdfjs from 'pdfjs-dist'

const API_URL = import.meta.env.VITE_API_URL as string

interface FamilyRowProps {
  node: FamilyNode
  selectedPatientId: number | null
  onPatientClick: (patient: PatientResp) => void
}

function FamilyRow({ node, selectedPatientId, onPatientClick }: FamilyRowProps) {
  return (
    <Collapsible.Root defaultOpen={false} className="w-full">
      <Collapsible.Trigger className="flex w-full items-center gap-1 rounded px-2 py-1 text-sm hover:bg-muted cursor-pointer group">
        <ChevronRightIcon className="size-3.5 transition-transform group-data-[state=open]:rotate-90" />
        <HomeIcon className="size-3.5 text-amber-500" />
        <span className="truncate">{node.family.identifier}</span>
        <span className="ml-auto text-xs text-muted-foreground">
          {node.patients.length}
        </span>
      </Collapsible.Trigger>
      <Collapsible.Panel className="pl-5 space-y-1">
        {node.patients.map((patient) => (
          <button
            key={patient.id}
            onClick={() => onPatientClick(patient)}
            className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-sm text-left hover:bg-muted cursor-pointer ${
              selectedPatientId === patient.id ? 'bg-muted font-medium' : ''
            }`}
          >
            <UserCircleIcon className="size-3.5 text-blue-400" />
            <span className="truncate">{patient.identifier}</span>
          </button>
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

  const [selectedPatient, setSelectedPatient] = useState<PatientResp | null>(null)
  const [highlights, setHighlights] = useState<Highlight[]>([])
  const pdfViewerRef = useRef<PdfViewerRef>(null)

  useEffect(() => {
    if (highlights.length > 0 && pdfViewerRef.current) {
      pdfViewerRef.current.scrollTo(highlights[0])
    }
  }, [highlights])

  const highlight = async ({ query, tableId, imageId }: HighlightArgs) => {
    if (!pdfViewerRef.current?.pdfDocument) return
    try {
      const result = await grobidAnnotationPapersPaperIdGrobidAnnotationPost({
        path: { paper_id: paperIdNum },
        body: {
          queries: [query],
          table_ids: tableId != null ? [tableId] : [],
          image_ids: imageId != null ? [imageId] : [],
          color: '#FFE28F',
        },
      })
      const annotations = (Array.isArray(result.data) ? result.data : result) as any[]
      const newHighlights = await annotationsToHighlights(
        pdfViewerRef.current.pdfDocument!,
        annotations,
        query,
      )
      setHighlights(newHighlights)
    } catch (err) {
      console.error('Failed to highlight:', err)
      setHighlights([])
    }
  }

  const handlePatientClick = async (patient: PatientResp) => {
    setSelectedPatient(patient)
    const query = (patient as any).identifier_evidence?.quote ?? patient.identifier
    if (query) highlight({ query })
  }

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

  const leftSidebar = (
    <>
      <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Families &amp; Patients
      </div>
      {familyNodes.length === 0 ? (
        <div className="px-2 text-sm text-muted-foreground">
          No families found.
        </div>
      ) : (
        familyNodes.map((node) => (
          <FamilyRow
            key={node.family.id}
            node={node}
            selectedPatientId={selectedPatient?.id ?? null}
            onPatientClick={handlePatientClick}
          />
        ))
      )}
    </>
  )

  const topRightPanel = selectedPatient ? (
    <PatientDetails patient={selectedPatient} paperId={paperIdNum} onHighlight={highlight} />
  ) : (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      Select a patient to view details
    </div>
  )

  if (!pdfUrl) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-muted-foreground">
          No PDF available.
        </div>
      </div>
    )
  }

  return (
    <TwoColumnWithBottomRightPdf
      left={leftSidebar}
      topRight={topRightPanel}
      pdfUrl={pdfUrl}
      pdfHighlights={highlights}
      pdfViewerRef={pdfViewerRef}
    />
  )
}
