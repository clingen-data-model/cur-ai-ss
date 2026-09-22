/* Per-row action to change (or clear) which HPO term a phenotype is linked
 * to -- for correcting a wrong auto-match or linking one manually where
 * extraction found none. Mirrors LinkVariantDialog's icon-button-trigger
 * shape but edits an existing row instead of creating a new link. The
 * trigger icon signals which of those two this is: a pencil for picking a
 * term for the first time ("manual edit"), a recycle icon for replacing an
 * existing one ("re-link") -- both open the same search-as-you-type
 * combobox and only ever accept a real ontology term either way. */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Pencil, Recycle } from 'lucide-react'
import { relinkPhenotypeHpoPapersPaperIdPhenotypesPhenotypeIdHpoPatch } from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { HpoCombobox } from '@/components/HpoCombobox'
import { apiErrorMessage } from '@/lib/apiError'

export function RelinkHpoDialog({
  paperId,
  phenotypeId,
  concept,
  currentHpoId,
  currentHpoName,
}: {
  paperId: number
  phenotypeId: number
  concept: string
  currentHpoId: string | null
  currentHpoName: string | null
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [hpoId, setHpoId] = useState<string | null>(currentHpoId)
  const hasExistingLink = currentHpoId != null

  const mutation = useMutation({
    mutationFn: (nextHpoId: string | null) =>
      relinkPhenotypeHpoPapersPaperIdPhenotypesPhenotypeIdHpoPatch({
        path: { paper_id: paperId, phenotype_id: phenotypeId },
        body: { hpo_id: nextHpoId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['phenotypes', paperId] })
      toast.success('HPO link updated')
      setOpen(false)
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to update HPO link')),
  })

  return (
    <>
      <button
        type="button"
        title={hasExistingLink ? 'Re-link HPO term' : 'Link HPO term'}
        onClick={(e) => {
          e.stopPropagation()
          setHpoId(currentHpoId)
          setOpen(true)
        }}
        className="inline-flex items-center justify-center size-7 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
      >
        {hasExistingLink ? <Recycle className="size-3.5" /> : <Pencil className="size-3.5" />}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent onClick={(e) => e.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>{hasExistingLink ? 'Re-link HPO Term' : 'Link HPO Term'}</DialogTitle>
            <DialogDescription>
              {hasExistingLink ? (
                <>
                  Change which HPO term{' '}
                  <span className="font-medium text-foreground">{concept}</span> is linked to, or
                  clear the link entirely.
                </>
              ) : (
                <>
                  Link <span className="font-medium text-foreground">{concept}</span> to an HPO
                  term.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label>HPO Term</Label>
            <HpoCombobox
              value={hpoId}
              initialLabel={currentHpoName}
              onValueChange={(id) => setHpoId(id)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => mutation.mutate(hpoId)}
              disabled={mutation.isPending || hpoId === currentHpoId}
            >
              {mutation.isPending ? 'Saving...' : hasExistingLink ? 'Save' : 'Link'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
