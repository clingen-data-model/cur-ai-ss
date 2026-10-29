/* Why nothing downstream ran: the paper classifier's verdict and its basis.
 *
 * A paper the classifier judged not relevant stops at that step, with its
 * successors never queued. The paper page then showed an empty Occurrences
 * tab behind a "hasn't run yet" gate and a FailedPaperRelevancy tag on the
 * papers list, while the one or two sentences saying which requirement the
 * paper failed were nowhere a curator could read them (paper 47, a mouse
 * Grxcr2 study, 2026-10-29). The handler stores that basis now and this
 * notice puts it at the top of the page, with the re-run dialog on the
 * classifier one click away for the case where the curator disagrees.
 */
import { CircleAlert } from 'lucide-react'
import { useState } from 'react'
import type { PaperResp } from '@/api/generated/types.gen'
import { RerunTaskDialog } from '@/components/PaperActions'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

/** Shown when the classifier judged the paper not relevant. A paper the
 * classifier has not judged, or judged relevant, renders nothing. */
export function PaperRelevanceNotice({ paper }: { paper: PaperResp }) {
  const [rerunOpen, setRerunOpen] = useState(false)
  if (paper.is_paper_relevant !== false) return null
  const basis = paper.is_paper_relevant_evidence?.reasoning

  return (
    <Alert variant="destructive">
      <CircleAlert />
      <AlertTitle>
        The paper classifier found no extractable cases for {paper.gene_symbol}
      </AlertTitle>
      <AlertDescription>
        <p>
          {basis ??
            'Its basis was not recorded for this run. Re-running the classifier records one.'}
        </p>
        <p>
          No extraction ran after it. If the paper does have identifiable cases
          for the gene, re-run the classifier with a note saying where they are.
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-1 w-fit"
          onClick={() => setRerunOpen(true)}
        >
          Re-run Paper Classifier
        </Button>
      </AlertDescription>
      <RerunTaskDialog
        paper={paper}
        open={rerunOpen}
        onOpenChange={setRerunOpen}
        initialTaskType="Paper Classifier"
      />
    </Alert>
  )
}
