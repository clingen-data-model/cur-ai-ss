/* The occurrence's own fields behind a row's expander: the ones the compact
 * occurrences table (Review Mode's family rail) has no column for. Testing
 * methods, disease name and the MONDO link are facts about the occurrence,
 * not about its patient or its variant, so neither of those panels could
 * hold them; on the paper page they are columns of the full table.
 *
 * The cells are the table's own, each with its popover; the row adds the
 * View in PDF icon the editable detail rows carry.
 */
import type { ReactNode } from 'react'
import type { PatientVariantOccurrenceResp } from '@/api/generated/types.gen'
import { ViewEvidenceButton, type EvidenceLike } from '@/components/EvidencePopover'
import {
  EditableDiseaseNameCell,
  EditableTestingMethodsCell,
  MondoDiseaseCell,
} from '@/components/OccurrenceEditableCells'

function Row({ label, evidence, children }: { label: string; evidence?: EvidenceLike | null; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 border-b last:border-0">
      <span className="text-sm text-muted-foreground shrink-0 w-44">{label}</span>
      <div className="flex items-center gap-1 flex-1 justify-end min-w-0">
        {children}
        <ViewEvidenceButton block={evidence} />
      </div>
    </div>
  )
}

export function OccurrenceDetailPanel({
  paperId,
  occurrence,
}: {
  paperId: number
  occurrence: PatientVariantOccurrenceResp
}) {
  return (
    <div className="p-4 bg-muted/30">
      <h4 className="text-sm font-semibold mb-2 max-w-xl">Occurrence</h4>
      <div className="max-w-xl">
        <Row label="Testing Methods" evidence={occurrence.testing_methods_evidence[0]}>
          <EditableTestingMethodsCell paperId={paperId} occurrence={occurrence} />
        </Row>
        <Row label="Disease Name" evidence={occurrence.disease_name_evidence}>
          <EditableDiseaseNameCell paperId={paperId} occurrence={occurrence} />
        </Row>
        <Row label="MONDO Disease" evidence={occurrence.mondo}>
          <MondoDiseaseCell occurrence={occurrence} />
        </Row>
      </div>
    </div>
  )
}
