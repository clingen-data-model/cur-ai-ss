/* Modal for linking an unassociated variant to an existing patient -- mirrors
 * LinkVariantDialog. The patient list is every patient on the paper, not just
 * unassociated ones: a patient can already have other variants linked (e.g. a
 * compound het pair) and still be a valid target here. */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Link2 } from 'lucide-react'
import {
  createOccurrencePapersPaperIdOccurrencesPost,
  getPatientsPapersPaperIdPatientsGet,
} from '@/api/generated'
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
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '@/components/ui/combobox'
import { apiErrorMessage } from '@/lib/apiError'

export function LinkPatientDialog({
  paperId,
  variantId,
  variantDescription,
}: {
  paperId: number
  variantId: number
  variantDescription: string
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [patientId, setPatientId] = useState<string | null>(null)
  const [draft, setDraft] = useState<string | null>(null)

  const patientsQuery = useQuery({
    queryKey: ['patients', paperId],
    queryFn: () => getPatientsPapersPaperIdPatientsGet({ path: { paper_id: paperId } }),
  })
  const patients = useMemo(() => patientsQuery.data ?? [], [patientsQuery.data])

  const labelFor = (id: string | null) => {
    if (id == null) return ''
    return patients.find((p) => String(p.id) === id)?.identifier ?? ''
  }
  const inputValue = draft ?? labelFor(patientId)

  const visible = useMemo(() => {
    const q = (draft ?? '').trim().toLowerCase()
    return q ? patients.filter((p) => p.identifier.toLowerCase().includes(q)) : patients
  }, [patients, draft])

  const reset = () => {
    setPatientId(null)
    setDraft(null)
  }

  const mutation = useMutation({
    mutationFn: () =>
      createOccurrencePapersPaperIdOccurrencesPost({
        path: { paper_id: paperId },
        body: { patient_id: Number(patientId), variant_id: variantId },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['occurrences', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Linked to patient')
      setOpen(false)
      reset()
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to link patient')),
  })

  return (
    <>
      <button
        type="button"
        title="Link to patient"
        onClick={(e) => {
          e.stopPropagation()
          setOpen(true)
        }}
        className="inline-flex items-center justify-center size-7 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
      >
        <Link2 className="size-4" />
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
            <DialogTitle>Link to Patient</DialogTitle>
            <DialogDescription>
              Link <span className="font-medium text-foreground">{variantDescription}</span> to
              an existing patient. Zygosity, inheritance, and other occurrence fields default
              and can be edited afterward.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label>Patient</Label>
            <Combobox
              value={patientId}
              itemToStringLabel={labelFor}
              inputValue={inputValue}
              onValueChange={(next: string | null) => {
                setPatientId(next)
                setDraft(labelFor(next))
              }}
              onInputValueChange={(next: string | null) => setDraft(next ?? '')}
            >
              <ComboboxInput placeholder="Search patients..." showClear autoFocus />
              <ComboboxContent>
                <ComboboxList>
                  {visible.map((p) => (
                    <ComboboxItem key={p.id} value={String(p.id)}>
                      {p.identifier}
                    </ComboboxItem>
                  ))}
                  <ComboboxEmpty>No matching patients.</ComboboxEmpty>
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => mutation.mutate()} disabled={!patientId || mutation.isPending}>
              {mutation.isPending ? 'Linking...' : 'Link'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
