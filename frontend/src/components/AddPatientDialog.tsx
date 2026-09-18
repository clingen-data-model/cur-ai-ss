/* Modal for manually adding a patient extraction didn't find. Only asks for an
 * identifier -- every other required PatientCreateRequest field (proband
 * status, sex, etc.) defaults to "Unknown", editable afterward like any other
 * extracted field. Every patient needs a family_id, so the curator picks an
 * existing family or creates a new one inline. */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import {
  createFamilyPapersPaperIdFamiliesPost,
  createPatientPapersPaperIdPatientsPost,
  getFamiliesPapersPaperIdFamiliesGet,
} from '@/api/generated'
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiErrorMessage } from '@/lib/apiError'

const NEW_FAMILY_VALUE = '__new__'

export function AddPatientDialog({ paperId }: { paperId: number }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [identifier, setIdentifier] = useState('')
  const [familyChoice, setFamilyChoice] = useState('')
  const [newFamilyName, setNewFamilyName] = useState('')

  const familiesQuery = useQuery({
    queryKey: ['families', paperId],
    queryFn: () => getFamiliesPapersPaperIdFamiliesGet({ path: { paper_id: paperId } }),
  })
  const families = familiesQuery.data ?? []
  const effectiveFamilyChoice =
    familyChoice || (families.length > 0 ? String(families[0].id) : NEW_FAMILY_VALUE)

  const reset = () => {
    setIdentifier('')
    setFamilyChoice('')
    setNewFamilyName('')
  }

  const mutation = useMutation({
    mutationFn: async () => {
      let familyId: number
      if (effectiveFamilyChoice === NEW_FAMILY_VALUE) {
        const family = await createFamilyPapersPaperIdFamiliesPost({
          path: { paper_id: paperId },
          body: { identifier: newFamilyName.trim() || `Family ${families.length + 1}` },
          throwOnError: true,
        })
        familyId = family.id
      } else {
        familyId = Number(effectiveFamilyChoice)
      }

      return createPatientPapersPaperIdPatientsPost({
        path: { paper_id: paperId },
        body: {
          family_id: familyId,
          identifier: identifier.trim(),
          proband_status: 'Unknown',
          affected_status: 'Unknown',
          sex: 'Unknown',
          country_of_origin: 'Unknown',
          race: 'Unknown',
          ethnicity: 'Unknown',
        },
        throwOnError: true,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['patients', paperId] })
      queryClient.invalidateQueries({ queryKey: ['families', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      toast.success('Patient added')
      setOpen(false)
      reset()
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to add patient')),
  })

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Plus className="size-4 mr-1.5" />
        Add Patient
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
            <DialogTitle>Add Patient</DialogTitle>
            <DialogDescription>
              Manually add a patient extraction didn't find. Demographic fields default to
              "Unknown" and can be edited afterward.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="patient-identifier">Identifier</Label>
              <Input
                id="patient-identifier"
                autoFocus
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="e.g. Patient 3, II-2"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Family</Label>
              <Select
                value={effectiveFamilyChoice}
                onValueChange={(value) => setFamilyChoice(value ?? '')}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {families.map((f) => (
                    <SelectItem key={f.id} value={String(f.id)}>
                      {f.identifier}
                    </SelectItem>
                  ))}
                  <SelectItem value={NEW_FAMILY_VALUE}>+ Create new family</SelectItem>
                </SelectContent>
              </Select>
              {effectiveFamilyChoice === NEW_FAMILY_VALUE && (
                <Input
                  value={newFamilyName}
                  onChange={(e) => setNewFamilyName(e.target.value)}
                  placeholder={`Family ${families.length + 1}`}
                />
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => mutation.mutate()}
              disabled={!identifier.trim() || mutation.isPending}
            >
              {mutation.isPending ? 'Adding...' : 'Add Patient'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
