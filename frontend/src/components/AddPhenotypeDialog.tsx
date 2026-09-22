/* Modal for manually adding a phenotype row extraction didn't find. Concept
 * text is required; the HPO term is optional and, when picked, is sent
 * straight to the create endpoint so the row starts out linked instead of
 * requiring a separate re-link afterward. */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import { createPhenotypePapersPaperIdPatientsPatientIdPhenotypesPost } from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

export function AddPhenotypeDialog({ paperId, patientId }: { paperId: number; patientId: number }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [concept, setConcept] = useState('')
  const [hpoId, setHpoId] = useState<string | null>(null)

  const reset = () => {
    setConcept('')
    setHpoId(null)
  }

  const mutation = useMutation({
    mutationFn: () =>
      createPhenotypePapersPaperIdPatientsPatientIdPhenotypesPost({
        path: { paper_id: paperId, patient_id: patientId },
        body: { concept: concept.trim(), hpo_id: hpoId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['phenotypes', paperId, patientId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Phenotype added')
      setOpen(false)
      reset()
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to add phenotype')),
  })

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Plus className="size-4 mr-1.5" />
        Add Phenotype
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) reset()
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Phenotype</DialogTitle>
            <DialogDescription>
              Manually add a phenotype extraction didn't find. Linking an HPO term now is
              optional -- it can also be added or changed later.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="phenotype-concept">Phenotype</Label>
              <Input
                id="phenotype-concept"
                autoFocus
                value={concept}
                onChange={(e) => setConcept(e.target.value)}
                placeholder="e.g. Seizures"
              />
            </div>
            <div className="space-y-1.5">
              <Label>HPO Term (optional)</Label>
              <HpoCombobox value={hpoId} onValueChange={(id) => setHpoId(id)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => mutation.mutate()}
              disabled={!concept.trim() || mutation.isPending}
            >
              {mutation.isPending ? 'Adding...' : 'Add Phenotype'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
