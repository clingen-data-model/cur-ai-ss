/* Modal for linking an unassociated patient to an existing variant --
 * creates the occurrence with just patient_id/variant_id; zygosity,
 * inheritance, de_novo, and testing_methods all default and are editable
 * afterward like any other occurrence field. The variant list is every
 * variant on the paper, not just unassociated ones: a variant can already be
 * linked to other patients (e.g. a shared recessive allele) and still be a
 * valid target here. */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Link2 } from 'lucide-react'
import {
  createOccurrencePapersPaperIdOccurrencesPost,
  getVariantsPapersPaperIdVariantsGet,
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

export function LinkVariantDialog({
  paperId,
  patientId,
  patientIdentifier,
}: {
  paperId: number
  patientId: number
  patientIdentifier: string
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [variantId, setVariantId] = useState<string | null>(null)
  const [draft, setDraft] = useState<string | null>(null)

  const variantsQuery = useQuery({
    queryKey: ['variants', paperId],
    queryFn: () => getVariantsPapersPaperIdVariantsGet({ path: { paper_id: paperId } }),
  })
  const variants = useMemo(() => variantsQuery.data ?? [], [variantsQuery.data])

  const labelFor = (id: string | null) => {
    if (id == null) return ''
    return variants.find((v) => String(v.id) === id)?.variant_description ?? ''
  }
  const inputValue = draft ?? labelFor(variantId)

  const visible = useMemo(() => {
    const q = (draft ?? '').trim().toLowerCase()
    return q
      ? variants.filter((v) => v.variant_description.toLowerCase().includes(q))
      : variants
  }, [variants, draft])

  const reset = () => {
    setVariantId(null)
    setDraft(null)
  }

  const mutation = useMutation({
    mutationFn: () =>
      createOccurrencePapersPaperIdOccurrencesPost({
        path: { paper_id: paperId },
        body: { patient_id: patientId, variant_id: Number(variantId) },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['occurrences', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Linked to variant')
      setOpen(false)
      reset()
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to link variant')),
  })

  return (
    <>
      <button
        type="button"
        title="Link to variant"
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
            <DialogTitle>Link to Variant</DialogTitle>
            <DialogDescription>
              Link <span className="font-medium text-foreground">{patientIdentifier}</span> to
              an existing variant. Zygosity, inheritance, and other occurrence fields default
              and can be edited afterward.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label>Variant</Label>
            <Combobox
              value={variantId}
              itemToStringLabel={labelFor}
              inputValue={inputValue}
              onValueChange={(next: string | null) => {
                setVariantId(next)
                setDraft(labelFor(next))
              }}
              onInputValueChange={(next: string | null) => setDraft(next ?? '')}
            >
              <ComboboxInput placeholder="Search variants..." showClear autoFocus />
              <ComboboxContent>
                <ComboboxList>
                  {visible.map((v) => (
                    <ComboboxItem key={v.id} value={String(v.id)}>
                      {v.variant_description}
                    </ComboboxItem>
                  ))}
                  <ComboboxEmpty>No matching variants.</ComboboxEmpty>
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => mutation.mutate()} disabled={!variantId || mutation.isPending}>
              {mutation.isPending ? 'Linking...' : 'Link'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
