/* Modal for manually adding a raw (unharmonized) variant extraction didn't
 * find. Only asks for the variant description -- type/functional evidence/
 * main focus all have server-side defaults, editable afterward like any
 * other extracted field. */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import { createVariantPapersPaperIdVariantsPost } from '@/api/generated'
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
import { apiErrorMessage } from '@/lib/apiError'

export function AddVariantDialog({ paperId }: { paperId: number }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [variant, setVariant] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      createVariantPapersPaperIdVariantsPost({
        path: { paper_id: paperId },
        body: { variant: variant.trim() },
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['variants', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Variant added')
      setOpen(false)
      setVariant('')
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to add variant')),
  })

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Plus className="size-4 mr-1.5" />
        Add Variant
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) setVariant('')
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Variant</DialogTitle>
            <DialogDescription>
              Manually add a raw variant extraction didn't find. Type and other properties
              default and can be edited afterward.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="variant-description">Variant</Label>
            <Input
              id="variant-description"
              autoFocus
              value={variant}
              onChange={(e) => setVariant(e.target.value)}
              placeholder="e.g. c.68_69delAG"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => mutation.mutate()}
              disabled={!variant.trim() || mutation.isPending}
            >
              {mutation.isPending ? 'Adding...' : 'Add Variant'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
