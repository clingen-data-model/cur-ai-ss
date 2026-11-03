/* Extraction page: the SPA's per-paper review surface, tabbed like the
 * Streamlit paper page (lib/ui/paper/header.py). "Occurrences" is the main
 * tab -- one row per patient/variant link, editable inline, with click-to-
 * expand Patient/Variant detail panels. The other three tabs surface what
 * didn't make it into an occurrence: patients/variants extraction found but
 * linking never connected, and the described figures (pedigree and
 * genotyping images).
 */
import { useState } from 'react'
import { useNavigate, useParams, useSearch, Link } from '@tanstack/react-router'
import { ClipboardCheck, FileText } from 'lucide-react'
import { usePaperOccurrences } from '@/hooks/usePaperOccurrences'
import { usePaperFlags } from '@/hooks/usePaperFlags'
import { FlagsTab } from '@/components/FlagsTab'
import { OccurrencesTab } from '@/components/OccurrencesTab'
import type { FlagTarget } from '@/lib/flagTarget'
import { DEFAULT_EXTRACTION_TAB, isExtractionTab, type ExtractionTab } from '@/lib/extractionTabs'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { API_BASE_URL, getAccessToken } from '@/lib/api'
import { UnassociatedPatientsTab } from '@/components/UnassociatedPatientsTab'
import { UnassociatedVariantsTab } from '@/components/UnassociatedVariantsTab'
import { PipelineGate } from '@/components/PipelineGate'
import { RestoreSnapshotButton } from '@/components/RestoreSnapshotButton'
import { PaperProgressPopover } from '@/components/PaperProgressPopover'
import { PaperRelevanceNotice } from '@/components/PaperRelevanceNotice'
import { ReviewStatusCell } from '@/components/ReviewStatusCell'
import { StatusBadge } from '@/components/StatusBadge'
import { computeStatus } from '@/lib/taskState'
import { TaskType } from '@/api/generated/types.gen'
import { FiguresTab } from '@/components/FiguresTab'
import { FamiliesTab } from '@/components/FamiliesTab'
import { PaperMetadataTab } from '@/components/PaperMetadataTab'
import { PdfHighlightProvider } from '@/components/PdfHighlightProvider'

/** What the Figure Descriptions tab can hold: the figure kinds extraction
 * reads for curation fields, as the tab's hover text. */
const FIGURE_DESCRIPTIONS_HINT =
  'The figures extraction reads: pedigrees, and genotyping images such as ' +
  'Sanger chromatograms, gels and restriction digests, copy-number plots ' +
  '(MLPA, array), sequencing read pileups, and karyotypes or FISH.'

export function ExtractionPage() {
  const params = useParams({ from: '/papers/$paperId/extraction' })
  const paperId = parseInt(params.paperId, 10)
  const {
    paper,
    rows,
    unassociatedPatients,
    unassociatedVariants,
    allPatients,
    allVariants,
    isLoading,
    isError,
    error,
  } = usePaperOccurrences(paperId)
  const flags = usePaperFlags(paperId)
  // The open tab lives in the URL so the papers table (and a pasted link)
  // can land on Families or Flags directly; the default stays out of it.
  const search = useSearch({ from: '/papers/$paperId/extraction' })
  const navigate = useNavigate({ from: '/papers/$paperId/extraction' })
  const tab: ExtractionTab = search.tab ?? DEFAULT_EXTRACTION_TAB
  const setTab = (next: string) => {
    if (!isExtractionTab(next)) return
    void navigate({ search: next === DEFAULT_EXTRACTION_TAB ? {} : { tab: next }, replace: true })
  }
  const [focus, setFocus] = useState<FlagTarget | null>(null)
  /** A flag's About chip: switch to the tab that shows the row, turn to its
   * page and open it. A patient or variant opens inside its first occurrence
   * (on its own panel) or, when it has none, in its Unassociated tab. A
   * family opens its row in the Families tab. */
  const navigateToTarget = (target: FlagTarget) => {
    const go = (next: ExtractionTab, to: FlagTarget) => {
      setFocus(to)
      setTab(next)
    }
    if (target.kind === 'occurrence') {
      go('occurrences', target)
    } else if (target.kind === 'patient') {
      const row = rows.find((r) => r.patient.id === target.id)
      if (row) go('occurrences', { kind: 'occurrence', id: row.occurrence.id, view: 'patient' })
      else go('unassociated-patients', target)
    } else if (target.kind === 'variant') {
      const row = rows.find((r) => r.variant.id === target.id)
      if (row) go('occurrences', { kind: 'occurrence', id: row.occurrence.id, view: 'variant' })
      else go('unassociated-variants', target)
    } else {
      go('families', target)
    }
  }
  const tasks = paper?.tasks ?? []
  const paperStatus = computeStatus(tasks)
  const [isExporting, setIsExporting] = useState(false)

  const handleExportPptx = async () => {
    setIsExporting(true)
    try {
      const token = getAccessToken()
      const headers: HeadersInit = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(`${API_BASE_URL}/papers/${paperId}/curation-export`, {
        headers,
      })
      if (!response.ok) throw new Error(`Failed to export PPTX: ${response.status}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `curation_${paperId}.pptx`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Error exporting PPTX:', err)
    } finally {
      setIsExporting(false)
    }
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

  return (
    <PdfHighlightProvider
      paperId={paperId}
      pdfUrl={paper?.pdf_url}
      filename={paper?.filename}
    >
      <div className="space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <Link to="/" className="text-sm text-muted-foreground hover:underline">
              &larr; All Papers
            </Link>
            <h1 className="text-xl font-semibold mt-1">{paper?.title ?? paper?.filename}</h1>
          </div>
          <div className="flex items-center gap-2">
            {/* Stacked in place of a standalone Re-run Agents button --
                PaperProgressPopover's own refresh icon already opens the
                same RerunTaskDialog, so a second control here was redundant. */}
            {paper && (
              <div className="flex items-center gap-2">
                <PaperProgressPopover
                  paper={{ id: paper.id, title: paper.title, filename: paper.filename, status: paperStatus }}
                >
                  <StatusBadge status={paperStatus} />
                </PaperProgressPopover>
                <ReviewStatusCell paper={paper} />
              </div>
            )}
            {paper && <RestoreSnapshotButton paper={paper} />}
            <Button
              variant="outline"
              size="sm"
              render={<Link to="/papers/$paperId/review" params={{ paperId: String(paperId) }} />}
              title="Walk the paper's cases beside the PDF and sign each off"
            >
              <ClipboardCheck className="h-4 w-4 mr-2" />
              Review Mode
              {paper?.signoff && (paper.signoff.total ?? 0) > 0 && (
                <span className="ml-1.5 text-xs text-muted-foreground tabular-nums">
                  {paper.signoff.confirmed ?? 0}/{paper.signoff.total ?? 0}
                </span>
              )}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportPptx}
              disabled={!paper || isExporting}
              title="Export curation summary as PPTX"
            >
              <FileText className="h-4 w-4 mr-2" />
              {isExporting ? 'Exporting...' : 'PPTX'}
            </Button>
          </div>
        </div>

        {paper && <PaperRelevanceNotice paper={paper} />}

        <Tabs
          value={tab}
          onValueChange={(next) => {
            // The reader chose this tab: a stale chip target must not reopen
            // a row when they come back to it.
            setFocus(null)
            setTab(String(next))
          }}
        >
          <TabsList>
            <TabsTrigger value="occurrences">Occurrences</TabsTrigger>
            <TabsTrigger value="families">Families</TabsTrigger>
            <TabsTrigger value="unassociated-patients">
              Unassociated Patients
              {unassociatedPatients.length > 0 && (
                <span className="ml-1 text-xs text-muted-foreground">({unassociatedPatients.length})</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="unassociated-variants">
              Unassociated Variants
              {unassociatedVariants.length > 0 && (
                <span className="ml-1 text-xs text-muted-foreground">({unassociatedVariants.length})</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="flags">
              Flags
              {flags.open.length > 0 && (
                <span className="ml-1 text-xs text-violet-700 dark:text-violet-400">({flags.open.length})</span>
              )}
            </TabsTrigger>
            <Tooltip>
              <TooltipTrigger render={<TabsTrigger value="figures">Figure Descriptions</TabsTrigger>} />
              <TooltipContent className="max-w-xs">{FIGURE_DESCRIPTIONS_HINT}</TooltipContent>
            </Tooltip>
            <TabsTrigger value="paper-metadata">Paper Metadata</TabsTrigger>
          </TabsList>

          <TabsContent value="occurrences" className="pt-3">
            <PipelineGate
              tasks={tasks}
              task={TaskType.PATIENT_VARIANT_OCCURRENCES}
              label="Patient/variant linking"
            >
              <OccurrencesTab
                paperId={paperId}
                rows={rows}
                flags={flags}
                focus={focus?.kind === 'occurrence' ? focus : null}
              />
            </PipelineGate>
          </TabsContent>
          <TabsContent value="families" className="pt-3">
            <PipelineGate tasks={tasks} task={TaskType.PATIENT_EXTRACTION} label="Patient extraction">
              <FamiliesTab
                paperId={paperId}
                focus={focus?.kind === 'family' || focus?.kind === 'patient' ? focus : null}
              />
            </PipelineGate>
          </TabsContent>
          <TabsContent value="unassociated-patients" className="pt-3">
            <UnassociatedPatientsTab
              paperId={paperId}
              patients={unassociatedPatients}
              allPatients={allPatients}
              tasks={tasks}
              flags={flags}
              focus={focus}
            />
          </TabsContent>
          <TabsContent value="unassociated-variants" className="pt-3">
            <UnassociatedVariantsTab
              paperId={paperId}
              variants={unassociatedVariants}
              tasks={tasks}
              flags={flags}
              focus={focus}
            />
          </TabsContent>
          <TabsContent value="flags" className="pt-3">
            <FlagsTab
              paperId={paperId}
              patients={allPatients}
              variants={allVariants}
              rows={rows}
              onNavigate={navigateToTarget}
            />
          </TabsContent>
          <TabsContent value="figures" className="pt-3">
            <FiguresTab paperId={paperId} />
          </TabsContent>
          <TabsContent value="paper-metadata" className="pt-3 h-[70vh]">
            {paper && <PaperMetadataTab paper={paper} />}
          </TabsContent>
        </Tabs>
      </div>
    </PdfHighlightProvider>
  )
}
