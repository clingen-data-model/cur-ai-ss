/* Per-row action to manually pair (or unpair) an occurrence with another
 * occurrence of the same patient, as a curator-confirmed compound-het pair.
 * Mirrors RelinkHpoDialog.tsx's shape closely: an icon-button trigger opening
 * a Dialog with two tabs -- "Pick a partner" writes straight to the pairing
 * via a dedicated PATCH endpoint (pairing is a symmetric two-row operation,
 * which the generic occurrence PATCH can't express), "Re-run agent" instead
 * queues COMPOUND_HET_EVALUATION for just this patient. The trigger icon
 * follows the same pencil-vs-refresh convention as RelinkHpoDialog: Link2 for
 * picking a partner for the first time, RefreshCw for changing an existing
 * pairing.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Link2, RefreshCw } from 'lucide-react'
import {
  createTaskPapersPaperIdTasksPost,
  pairOccurrencePapersPaperIdOccurrencesOccurrenceIdPairPatch,
} from '@/api/generated'
import { TaskType } from '@/api/generated/types.gen'
import type { PatientVariantOccurrenceResp } from '@/api/generated/types.gen'
import type { OccurrenceRow } from '@/hooks/usePaperOccurrences'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiErrorMessage } from '@/lib/apiError'

const NONE_VALUE = '__none__'

export function PairOccurrenceDialog({
  paperId,
  occurrence,
  siblingOccurrences,
}: {
  paperId: number
  occurrence: PatientVariantOccurrenceResp
  siblingOccurrences: OccurrenceRow[]
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const currentPartnerId = occurrence.paired_variant_link_id ?? null
  const [partnerId, setPartnerId] = useState<number | null>(currentPartnerId)
  const [context, setContext] = useState('')
  const hasExistingPairing = currentPartnerId != null

  const reset = () => {
    setPartnerId(currentPartnerId)
    setContext('')
  }

  const pairMutation = useMutation({
    mutationKey: ['paper-edit', paperId],
    mutationFn: (nextPartnerId: number | null) =>
      pairOccurrencePapersPaperIdOccurrencesOccurrenceIdPairPatch({
        path: { paper_id: paperId, occurrence_id: occurrence.id },
        body: { paired_occurrence_id: nextPartnerId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['occurrences', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Pairing updated')
      setOpen(false)
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to update pairing')),
  })

  const rerunMutation = useMutation({
    mutationFn: () =>
      createTaskPapersPaperIdTasksPost({
        path: { paper_id: paperId },
        body: {
          type: TaskType.COMPOUND_HET_EVALUATION,
          patient_id: occurrence.patient_id,
          additional_context: context.trim() || null,
          skip_successors: false,
        },
        throwOnError: true,
      }),
    onSuccess: () => {
      toast.success('Compound het evaluation agent queued')
      setOpen(false)
      setContext('')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to queue agent re-run')),
  })

  return (
    <>
      <button
        type="button"
        title={hasExistingPairing ? 'Change pairing' : 'Pair variant'}
        onClick={(e) => {
          e.stopPropagation()
          reset()
          setOpen(true)
        }}
        className="inline-flex items-center justify-center size-7 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
      >
        {hasExistingPairing ? <RefreshCw className="size-3.5" /> : <Link2 className="size-3.5" />}
      </button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) reset()
        }}
      >
        <DialogContent onClick={(e) => e.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>{hasExistingPairing ? 'Change Pairing' : 'Pair Variant'}</DialogTitle>
            <DialogDescription>
              Mark this occurrence as compound heterozygous with another occurrence of the same
              patient.
            </DialogDescription>
          </DialogHeader>
          <Tabs defaultValue="pick">
            <TabsList>
              <TabsTrigger value="pick">Pick a partner</TabsTrigger>
              <TabsTrigger value="agent">Re-run agent</TabsTrigger>
            </TabsList>
            <TabsContent value="pick" className="space-y-4 pt-3">
              <div className="space-y-1.5">
                <Label>Partner Occurrence</Label>
                {siblingOccurrences.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No other occurrences for this patient.
                  </p>
                ) : (
                  <Select
                    value={partnerId == null ? NONE_VALUE : String(partnerId)}
                    onValueChange={(v) => setPartnerId(v === NONE_VALUE ? null : Number(v))}
                  >
                    <SelectTrigger className="w-full">
                      {/* base-ui's Select.Value renders the raw value string unless
                          given a render-prop -- it doesn't look up a SelectItem's
                          children to derive a label. */}
                      <SelectValue>
                        {(value: string) =>
                          value === NONE_VALUE
                            ? '— No pairing —'
                            : (siblingOccurrences.find(
                                (sibling) => String(sibling.occurrence.id) === value,
                              )?.variant.variant_description ?? value)
                        }
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE_VALUE}>— No pairing —</SelectItem>
                      {siblingOccurrences.map((sibling) => (
                        <SelectItem key={sibling.occurrence.id} value={String(sibling.occurrence.id)}>
                          {sibling.variant.variant_description}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => pairMutation.mutate(partnerId)}
                  disabled={
                    pairMutation.isPending ||
                    partnerId === currentPartnerId ||
                    siblingOccurrences.length === 0
                  }
                >
                  {pairMutation.isPending ? 'Saving...' : 'Save'}
                </Button>
              </DialogFooter>
            </TabsContent>
            <TabsContent value="agent" className="space-y-4 pt-3">
              <div className="space-y-1.5">
                <Label>
                  Additional context{' '}
                  <span className="text-muted-foreground font-normal">(optional)</span>
                </Label>
                <Textarea
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  placeholder="Any specific instructions for the agent's next attempt..."
                  rows={3}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Re-runs compound-het evaluation for this patient in the background. The result
                will show up here once it's done.
              </p>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={() => rerunMutation.mutate()} disabled={rerunMutation.isPending}>
                  {rerunMutation.isPending ? 'Queuing...' : 'Re-run agent'}
                </Button>
              </DialogFooter>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  )
}
