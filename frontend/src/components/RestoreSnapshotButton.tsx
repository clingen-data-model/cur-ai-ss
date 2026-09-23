/* Restore a paper's extracted data to a saved snapshot.
 *
 * Ports lib/ui/paper/header.py's render_reset_fragment to the SPA: a
 * snapshot is written after every completed pipeline cycle and right before
 * every rerun (so an edit made between the two is never silently lost to
 * the rerun's delete-and-recreate), and restoring replaces the paper's data
 * -- entities, links, edit history, deletions, and task history -- exactly
 * as that snapshot recorded it. Same two endpoints Streamlit already uses:
 * GET /papers/{id}/snapshots, POST /papers/{id}/reset.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { History } from 'lucide-react'
import {
  getPaperSnapshotsPapersPaperIdSnapshotsGet,
  resetPaperPapersPaperIdResetPost,
} from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { apiErrorMessage } from '@/lib/apiError'
import type { PaperResp, SnapshotMeta } from '@/api/generated/types.gen'

// Mirrors lib/tasks/models.py's ACTIVE_STATUSES -- the same statuses the
// reset endpoint's own 409 guard checks server-side.
const ACTIVE_TASK_STATUSES = new Set(['Pending', 'Queued', 'Running'])

function formatSnapshotLabel(snapshot: SnapshotMeta): string {
  const created = new Date(snapshot.created_at)
  const parts = [`${created.toISOString().slice(0, 16).replace('T', ' ')} UTC`]
  if (snapshot.description) parts.push(snapshot.description)
  if (snapshot.model) parts.push(snapshot.model)
  if (snapshot.matches_current) parts.push('current state')
  return parts.join(' — ')
}

function RestoreSnapshotDialog({
  paper,
  open,
  onOpenChange,
}: {
  paper: PaperResp
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [selectedName, setSelectedName] = useState<string | null>(null)

  const snapshotsQuery = useQuery({
    queryKey: ['paper-snapshots', paper.id],
    queryFn: () =>
      getPaperSnapshotsPapersPaperIdSnapshotsGet({
        path: { paper_id: paper.id },
        throwOnError: true,
      }),
    // Fetches as soon as this (always-mounted) dialog wrapper mounts, not
    // gated on `open`: this is now a cheap indexed query (see
    // lib/misc/snapshots.py's list_snapshots), so by the time a curator
    // actually opens the dialog the list is already cached and there's no
    // "Loading snapshots..." flash resizing the dialog on first open.
  })

  const snapshots = snapshotsQuery.data ?? []
  // Default to the snapshot matching current state (harmless to re-apply),
  // so restoring anything else is a deliberate choice -- same reasoning as
  // header.py's default_index.
  const defaultName = snapshots.find((s) => s.matches_current)?.name ?? snapshots[0]?.name ?? null
  const chosenName = selectedName ?? defaultName
  const chosen = snapshots.find((s) => s.name === chosenName) ?? null

  const mutation = useMutation({
    mutationFn: (snapshotName: string) =>
      resetPaperPapersPaperIdResetPost({
        path: { paper_id: paper.id },
        body: { snapshot_name: snapshotName },
        throwOnError: true,
      }),
    onSuccess: (result) => {
      // A reset touches everything about this paper at once -- patients,
      // variants, occurrences, pedigree, tasks, metadata -- broader than any
      // single hook's query key, so invalidate everything scoped to this
      // paper rather than hunting down each one by hand.
      queryClient.invalidateQueries({
        predicate: (q) => Array.isArray(q.queryKey) && q.queryKey[1] === paper.id,
      })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      if (result.changed) {
        toast.success('Paper reset to extraction snapshot')
      } else {
        toast.info('Paper already matches this snapshot — nothing to reset')
      }
      onOpenChange(false)
      setSelectedName(null)
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to reset paper')),
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setSelectedName(null)
        onOpenChange(next)
      }}
    >
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-semibold">Restore Snapshot</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              {paper.title ?? paper.filename}
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            Each time the extraction pipeline finishes, and right before any agent
            rerun, the extracted data (patients, variants, phenotypes, links, ...) is
            saved as a snapshot. Restoring replaces the paper's data exactly as the
            chosen snapshot recorded it, discarding anything from after it.
          </p>
          {snapshotsQuery.isPending ? (
            <p className="text-sm text-muted-foreground">Loading snapshots...</p>
          ) : snapshots.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No extraction snapshots yet. A snapshot is written each time the
              extraction pipeline completes.
            </p>
          ) : (
            <>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Restore snapshot</label>
                <Select value={chosenName ?? undefined} onValueChange={setSelectedName}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-60">
                    {snapshots.map((s) => (
                      <SelectItem
                        key={s.name}
                        value={s.name}
                        className="items-start py-1.5 text-xs [&_span]:min-w-0 [&_span]:shrink [&_span]:whitespace-normal [&_span]:break-words"
                      >
                        {formatSnapshotLabel(s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="text-sm text-muted-foreground">
                ⚠️ Resetting cannot be undone. Task history reverts with the
                snapshot. Note that you cannot restore to a snapshot that
                matches the existing curation.
              </p>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => chosenName && mutation.mutate(chosenName)}
                  disabled={!chosenName || !!chosen?.matches_current || mutation.isPending}
                  title={
                    chosen?.matches_current
                      ? 'The paper already matches this snapshot'
                      : undefined
                  }
                >
                  {mutation.isPending ? 'Restoring...' : 'Restore'}
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function RestoreSnapshotButton({ paper }: { paper: PaperResp }) {
  const [open, setOpen] = useState(false)
  const isActive = paper.tasks?.some((t) => ACTIVE_TASK_STATUSES.has(t.status)) ?? false

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={isActive}
        title={
          isActive
            ? 'Cannot restore while extraction tasks are pending or running'
            : 'Restore a saved extraction snapshot'
        }
      >
        <History className="h-4 w-4 mr-2" />
        Restore Snapshot
      </Button>
      <RestoreSnapshotDialog paper={paper} open={open} onOpenChange={setOpen} />
    </>
  )
}
