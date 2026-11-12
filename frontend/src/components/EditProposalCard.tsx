import { ArrowRightIcon, CheckIcon, MinusIcon, PencilIcon, PlusIcon, XIcon } from 'lucide-react'
import type { ChatMessageResp, ProposedEdit } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

/* The confirmation for direct edits the paper chat proposed. Nothing has
 * been changed when it opens: the curator reads what will happen, in a
 * section per kind of row, and confirms every change (or cancels).
 * Closing it leaves the proposal pending; the chat keeps a "Review" button
 * for it, and once it is resolved, a line saying who confirmed or
 * cancelled it. A direct edit is the curator's own change, as the paper
 * page's forms make it -- unlike a re-run, which reads the paper again and
 * replaces what it wrote. */

const ACTIONS: Record<ProposedEdit['action'], { label: string; icon: typeof PlusIcon; tone: string }> = {
  create: {
    label: 'Add',
    icon: PlusIcon,
    tone: 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  },
  update: {
    label: 'Change',
    icon: PencilIcon,
    tone: 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200',
  },
  delete: {
    label: 'Remove',
    icon: MinusIcon,
    tone: 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200',
  },
}

// Curators see "individual" where the API says patient (see taskLabel).
const ENTITY_NOUN: Record<ProposedEdit['entity'], string> = {
  family: 'family',
  patient: 'individual',
  variant: 'variant',
  occurrence: 'occurrence',
  phenotype: 'phenotype',
}

/* The dialog's sections, one per kind of row. A phenotype belongs to an
 * individual, so its edits sit under that individual with the edits to the
 * individual themselves. */
const SECTIONS: { title: string; entities: ProposedEdit['entity'][] }[] = [
  { title: 'Families', entities: ['family'] },
  { title: 'Individuals', entities: ['patient', 'phenotype'] },
  { title: 'Variants', entities: ['variant'] },
  { title: 'Occurrences', entities: ['occurrence'] },
]

/* The individual an Individuals-section edit is about, as "Family 2 II-3":
 * an individual's own edit is labelled by identifier and owned by its
 * family; a phenotype's is owned by the individual. */
function individualOf(edit: ProposedEdit): string {
  return edit.entity === 'patient'
    ? [edit.owner_label, edit.label].filter(Boolean).join(' ')
    : (edit.owner_label ?? '')
}

function byIndividual(edits: ProposedEdit[]): [string, ProposedEdit[]][] {
  const groups = new Map<string, ProposedEdit[]>()
  for (const edit of edits) {
    const key = individualOf(edit)
    groups.set(key, [...(groups.get(key) ?? []), edit])
  }
  return [...groups.entries()]
}

function rowTitle(edit: ProposedEdit): string {
  // An occurrence is both halves: who carries it, and which variant.
  return edit.entity === 'occurrence' && edit.owner_label
    ? `${edit.owner_label}: ${edit.label}`
    : edit.label
}

function EditList({ edits }: { edits: ProposedEdit[] }) {
  return (
    <ul className="space-y-2">
      {edits.map((edit, i) => (
        <EditRow key={`${edit.entity}-${edit.entity_id ?? 'new'}-${i}`} edit={edit} />
      ))}
    </ul>
  )
}

function EditRow({ edit }: { edit: ProposedEdit }) {
  const action = ACTIONS[edit.action]
  const Icon = action.icon
  // A new row is named by its label, so the field that label came from
  // (an individual's identifier, a phenotype's concept) is not repeated.
  const changes = (edit.changes ?? []).filter(
    (change) => !(edit.action === 'create' && change.new === edit.label),
  )
  return (
    <li className="space-y-1">
      <div className="flex items-center gap-2">
        <Badge variant="outline" className={cn('gap-1 font-medium', action.tone)}>
          <Icon className="size-3" />
          {action.label}
        </Badge>
        <span className={cn('font-medium', edit.action === 'delete' && 'line-through decoration-rose-500/70')}>
          {rowTitle(edit)}
        </span>
        <span className="text-xs text-muted-foreground">{ENTITY_NOUN[edit.entity]}</span>
      </div>
      {changes.length > 0 && (
        <dl className="ml-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 border-l pl-3 text-xs">
          {changes.map((change) => (
            <div key={change.field} className="contents">
              <dt className="text-muted-foreground">{change.label}</dt>
              <dd className="flex flex-wrap items-center gap-1">
                {change.old != null && (
                  <>
                    <span className="text-muted-foreground line-through">{change.old}</span>
                    <ArrowRightIcon className="size-3 text-muted-foreground" />
                  </>
                )}
                <span>{change.new ?? <em className="text-muted-foreground">none</em>}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}
      {edit.citation && (
        <blockquote className="ml-1 border-l-2 border-primary/40 pl-3 text-xs text-muted-foreground">
          “{edit.citation.quote}”
          <span className="ml-1 whitespace-nowrap">— {edit.citation.anchor}</span>
        </blockquote>
      )}
    </li>
  )
}

function changesNoun(count: number): string {
  return count === 1 ? 'change' : `${count} changes`
}

/* Under a chat reply: a button to (re)open the dialog while the proposal
 * is pending, then who confirmed or cancelled it. */
export function ProposalStatus({
  message,
  onReview,
}: {
  message: ChatMessageResp
  onReview: () => void
}) {
  const proposal = message.proposal
  if (!proposal) return null
  const count = proposal.edits?.length ?? 0
  if (message.proposal_status === 'pending') {
    return (
      <Button variant="outline" size="sm" className="mt-2" onClick={onReview}>
        Review {changesNoun(count)}
      </Button>
    )
  }
  const applied = message.proposal_status === 'applied'
  return (
    <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
      {applied ? <CheckIcon className="size-3.5 text-emerald-600" /> : <XIcon className="size-3.5" />}
      {applied ? `Applied ${changesNoun(count)}` : 'Cancelled'}
      {proposal.resolved_by_name ? ` by ${proposal.resolved_by_name}` : ''}
      {message.proposal_resolved_at
        ? ` · ${new Date(message.proposal_resolved_at).toLocaleString()}`
        : ''}
    </p>
  )
}

export function EditProposalDialog({
  message,
  onOpenChange,
  onApply,
  onCancel,
  isApplying,
  isCancelling,
}: {
  message: ChatMessageResp | null
  onOpenChange: (open: boolean) => void
  onApply: () => void
  onCancel: () => void
  isApplying: boolean
  isCancelling: boolean
}) {
  const edits = message?.proposal?.edits ?? []
  const count = edits.length
  const busy = isApplying || isCancelling

  return (
    <Dialog open={message != null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Confirm {count === 1 ? 'this change' : `these ${count} changes`}</DialogTitle>
          <DialogDescription>
            Nothing has changed yet. Confirming records {count === 1 ? 'it' : 'them'} as your
            edit{count === 1 ? '' : 's'}, with your message as the note.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto">
          {SECTIONS.map(({ title, entities }) => {
            const inSection = edits.filter((edit) => entities.includes(edit.entity))
            if (inSection.length === 0) return null
            return (
              <section key={title} className="space-y-1.5">
                <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {title}
                </h4>
                {title === 'Individuals' ? (
                  byIndividual(inSection).map(([individual, group]) => (
                    <div key={individual} className="space-y-1.5 border-l pl-3">
                      <p className="text-xs font-medium">{individual}</p>
                      <EditList edits={group} />
                    </div>
                  ))
                ) : (
                  <EditList edits={inSection} />
                )}
              </section>
            )
          })}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            {isCancelling ? <Spinner className="size-3" /> : <XIcon />}
            Cancel {count === 1 ? 'change' : 'changes'}
          </Button>
          <Button onClick={onApply} disabled={busy}>
            {isApplying ? <Spinner className="size-3" /> : <CheckIcon />}
            {count === 1 ? 'Confirm change' : `Confirm ${count} changes`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
