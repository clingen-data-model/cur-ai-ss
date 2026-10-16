/* Family structure and segregation analysis, one card per family -- the SPA
 * replacement for the last Streamlit view (lib/ui/paper/patients.py's
 * _render_family_group).
 *
 * A family's detail shows the family's own fields (identifier, consanguinity), its
 * members as a pedigree-style table, and the segregation analysis: the two
 * values the extraction agent collected from the paper (editable, with an
 * edit note) and the six the computation agent derived from the family's
 * patients and variants (read-only, each with its reasoning).
 *
 * The data has no parent/child links, only each person's relationship to the
 * proband, so members are grouped by that relationship rather than drawn as a
 * tree; the paper's own figure is on the Pedigree tab.
 *
 * Families are listed in a table, one row each, with the caret that opens a
 * row's detail (the same expander as the occurrences table); the row shows the
 * counts and the segregation verdict, the open detail is everything above.
 *
 * Like Streamlit, a family with a single patient is not shown: it has no
 * structure and no segregation to speak of.
 */
import { Fragment, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  getFamiliesPapersPaperIdFamiliesGet,
  getPatientsPapersPaperIdPatientsGet,
  getSegregationAnalysisPapersPaperIdSegregationAnalysisGet,
  updateFamilyPapersPaperIdFamiliesFamilyIdPatch,
  updateSegregationEvidencePapersPaperIdSegregationAnalysisFamilyIdPatch,
} from '@/api/generated'
import { TaskType } from '@/api/generated/types.gen'
import type {
  FamilyResp,
  FamilyUpdateRequest,
  PatientResp,
  SegregationAnalysisResp,
  SegregationEvidenceUpdateRequest,
} from '@/api/generated/types.gen'
import { EditableNumberRow, EditableSwitchRow, EditableTextRow, ReadOnlyRow } from '@/components/EditableField'
import { FlagIndicator } from '@/components/FlagIndicator'
import { usePaperFlags } from '@/hooks/usePaperFlags'
import type { FlagIndex } from '@/hooks/usePaperFlags'
import { PatientIdCell } from '@/components/PatientIdCell'
import { RowExpander } from '@/components/RowExpander'
import { PatientDetailPanel } from '@/components/PatientDetailPanel'
import { ScopedRerunButton } from '@/components/ScopedRerunButton'
import { Badge } from '@/components/ui/badge'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { apiErrorMessage } from '@/lib/apiError'

const STALE_TIME = 5 * 60 * 1000

/** Parents first, then the proband's generation, then children -- the closest
 * reading of a pedigree's rows the stored relationships allow. */
const RELATIONSHIP_ORDER = ['Parent', 'Proband', 'Sibling', 'Half-Sibling', 'Child', 'Other', 'Unknown']

function relationshipRank(patient: PatientResp): number {
  const label = patient.relationship_to_proband ?? 'Unknown'
  const rank = RELATIONSHIP_ORDER.indexOf(label)
  return rank === -1 ? RELATIONSHIP_ORDER.length : rank
}

function formatNumber(value: number, digits = 2): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(digits)
}

function FamilyMembers({
  paperId,
  members,
  flags,
  focusPatientId,
}: {
  paperId: number
  members: PatientResp[]
  flags: FlagIndex
  /** A member to open on arrival (from a flag's About chip). */
  focusPatientId?: number | null
}) {
  const [expandedId, setExpandedId] = useState<number | null>(focusPatientId ?? null)
  useEffect(() => {
    if (focusPatientId != null) setExpandedId(focusPatientId)
  }, [focusPatientId])
  const sorted = [...members].sort(
    (a, b) => relationshipRank(a) - relationshipRank(b) || a.identifier.localeCompare(b.identifier, undefined, { numeric: true }),
  )
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8" />
          <TableHead className="w-8" />
          <TableHead>Patient</TableHead>
          <TableHead>Relationship</TableHead>
          <TableHead>Carrier</TableHead>
          <TableHead>Twin</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((patient) => {
          const expanded = expandedId === patient.id
          return (
            <Fragment key={patient.id}>
              <TableRow
                className="cursor-pointer"
                onClick={() => setExpandedId(expanded ? null : patient.id)}
              >
                <TableCell>
                  <RowExpander expanded={expanded} onToggle={() => setExpandedId(expanded ? null : patient.id)} />
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <FlagIndicator paperId={paperId} flags={flags.byPatient.get(patient.id) ?? []} />
                </TableCell>
                <TableCell className="font-medium">
                  <PatientIdCell
                    paperId={paperId}
                    patient={patient}
                    onClick={() => setExpandedId(expanded ? null : patient.id)}
                  />
                </TableCell>
                <TableCell>{patient.relationship_to_proband ?? '—'}</TableCell>
                <TableCell>
                  {patient.is_obligate_carrier == null ? '—' : patient.is_obligate_carrier ? 'Obligate' : 'No'}
                </TableCell>
                <TableCell>{patient.twin_type ?? '—'}</TableCell>
              </TableRow>
              {expanded && (
                <TableRow>
                  <TableCell colSpan={6} className="p-0">
                    <PatientDetailPanel paperId={paperId} patient={patient} />
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}

function SegregationSection({
  paperId,
  family,
  seg,
}: {
  paperId: number
  family: FamilyResp
  seg: SegregationAnalysisResp
}) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationKey: ['paper-edit', paperId],
    mutationFn: (body: SegregationEvidenceUpdateRequest) =>
      updateSegregationEvidencePapersPaperIdSegregationAnalysisFamilyIdPatch({
        path: { paper_id: paperId, family_id: family.id },
        body,
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segregation-analysis', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to save segregation evidence')),
  })
  const computed = seg.computed

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Segregation analysis</h4>
        <ScopedRerunButton
          paperId={paperId}
          taskType={TaskType.SEGREGATION_EVIDENCE_EXTRACTION}
          scope={{ family_id: family.id }}
          label="Re-run segregation"
          description="Re-runs segregation evidence extraction for this family, then recomputes the analysis."
        />
      </div>

      <div className="max-w-2xl">
        <EditableNumberRow
          label="Extracted LOD score"
          value={seg.extracted_lod_score.value}
          evidence={seg.extracted_lod_score}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            mutation.mutate({ extracted_lod_score: value, extracted_lod_score_human_edit_note: note })
          }
        />
        <EditableSwitchRow
          label="Unexplainable non-segregations"
          value={seg.has_unexplainable_non_segregations.value}
          evidence={seg.has_unexplainable_non_segregations}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            mutation.mutate({
              has_unexplainable_non_segregations: value,
              has_unexplainable_non_segregations_human_edit_note: note,
            })
          }
        />
      </div>

      {computed ? (
        <div className="max-w-2xl pt-2">
          <p className="text-xs text-muted-foreground pb-1">Computed from this family's patients and variants</p>
          <ReadOnlyRow
            label="Meets minimum criteria"
            value={
              computed.meets_minimum_criteria.value ? (
                <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100" variant="outline">
                  Met
                </Badge>
              ) : (
                <Badge className="bg-rose-100 text-rose-800 hover:bg-rose-100" variant="outline">
                  Not met
                </Badge>
              )
            }
            evidence={computed.meets_minimum_criteria}
          />
          <ReadOnlyRow
            label="Segregation count"
            value={formatNumber(computed.segregation_count.value)}
            evidence={computed.segregation_count}
          />
          <ReadOnlyRow
            label="Affected count"
            value={formatNumber(computed.affected_count.value)}
            evidence={computed.affected_count}
          />
          <ReadOnlyRow
            label="Unaffected count"
            value={formatNumber(computed.unaffected_count.value)}
            evidence={computed.unaffected_count}
          />
          <ReadOnlyRow
            label="Computed LOD score"
            value={formatNumber(computed.computed_lod_score.value)}
            evidence={computed.computed_lod_score}
          />
          <ReadOnlyRow
            label="Points assigned"
            value={formatNumber(computed.points_assigned.value)}
            evidence={computed.points_assigned}
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">The analysis has not been computed for this family yet.</p>
      )}
    </div>
  )
}

function FamilyDetail({
  paperId,
  family,
  members,
  seg,
  flags,
  focusPatientId,
}: {
  paperId: number
  family: FamilyResp
  members: PatientResp[]
  seg: SegregationAnalysisResp | undefined
  flags: FlagIndex
  focusPatientId?: number | null
}) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationKey: ['paper-edit', paperId],
    mutationFn: (body: FamilyUpdateRequest) =>
      updateFamilyPapersPaperIdFamiliesFamilyIdPatch({
        path: { paper_id: paperId, family_id: family.id },
        body,
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['families', paperId] })
      // Patients carry family_identifier, so a rename shows there too.
      queryClient.invalidateQueries({ queryKey: ['patients', paperId] })
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to save family')),
  })

  return (
    <div className="p-4 space-y-4">
      <div className="max-w-2xl">
        <EditableTextRow
          label="Family identifier"
          value={family.identifier}
          evidence={family.identifier_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) => mutation.mutate({ identifier: value, identifier_human_edit_note: note })}
        />
        <EditableSwitchRow
          label="Consanguinity"
          value={family.consanguinity}
          evidence={family.consanguinity_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) => mutation.mutate({ consanguinity: value, consanguinity_human_edit_note: note })}
        />
      </div>

      <FamilyMembers paperId={paperId} members={members} flags={flags} focusPatientId={focusPatientId} />

      {seg ? (
        <SegregationSection paperId={paperId} family={family} seg={seg} />
      ) : (
        <p className="text-sm text-muted-foreground">No segregation analysis for this family yet.</p>
      )}
    </div>
  )
}

function FamilyRow({
  paperId,
  family,
  members,
  seg,
  flags,
  expanded,
  onToggle,
  focus,
}: {
  paperId: number
  family: FamilyResp
  members: PatientResp[]
  seg: SegregationAnalysisResp | undefined
  flags: FlagIndex
  expanded: boolean
  onToggle: () => void
  focus?: FamilyFocus | null
}) {
  const focused =
    focus != null &&
    ((focus.kind === 'family' && focus.id === family.id) ||
      (focus.kind === 'patient' && members.some((m) => m.id === focus.id)))
  const rowRef = useRef<HTMLTableRowElement>(null)
  useEffect(() => {
    if (focused) rowRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [focused, focus])

  const affected = members.filter((p) => p.affected_status === 'Affected').length
  const unaffected = members.filter((p) => p.affected_status === 'Unaffected').length
  const unknown = members.length - affected - unaffected
  const criteria = seg?.computed?.meets_minimum_criteria

  return (
    <Fragment>
      <TableRow ref={rowRef} className="cursor-pointer scroll-mt-4" onClick={onToggle}>
        <TableCell>
          <RowExpander expanded={expanded} onToggle={onToggle} />
        </TableCell>
        <TableCell onClick={(e) => e.stopPropagation()}>
          <FlagIndicator paperId={paperId} flags={flags.byFamily.get(family.id) ?? []} />
        </TableCell>
        <TableCell className="font-medium">{family.identifier}</TableCell>
        <TableCell>{members.length}</TableCell>
        <TableCell>{affected}</TableCell>
        <TableCell>{unaffected}</TableCell>
        <TableCell>{unknown}</TableCell>
        <TableCell>{family.consanguinity ? 'Yes' : 'No'}</TableCell>
        <TableCell>
          {criteria ? (
            <Badge
              variant="outline"
              className={criteria.value ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}
            >
              {criteria.value ? 'Met' : 'Not met'}
            </Badge>
          ) : (
            '—'
          )}
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={9} className="p-0">
            <FamilyDetail
              paperId={paperId}
              family={family}
              members={members}
              seg={seg}
              flags={flags}
              focusPatientId={focused && focus?.kind === 'patient' ? focus.id : null}
            />
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  )
}

/** The family or patient a flag's About chip asked to open. */
export type FamilyFocus = { kind: 'family'; id: number } | { kind: 'patient'; id: number }

export function FamiliesTab({ paperId, focus }: { paperId: number; focus?: FamilyFocus | null }) {
  const flags = usePaperFlags(paperId)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const familiesQuery = useQuery({
    queryKey: ['families', paperId],
    queryFn: () => getFamiliesPapersPaperIdFamiliesGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })
  const patientsQuery = useQuery({
    queryKey: ['patients', paperId],
    queryFn: () => getPatientsPapersPaperIdPatientsGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })
  const segregationQuery = useQuery({
    queryKey: ['segregation-analysis', paperId],
    queryFn: () => getSegregationAnalysisPapersPaperIdSegregationAnalysisGet({ path: { paper_id: paperId } }),
    staleTime: STALE_TIME,
  })

  const families = familiesQuery.data
  const patients = patientsQuery.data
  const segregation = segregationQuery.data

  // A flag's About chip opens the family it names, or the patient's family.
  const focusedFamilyId =
    focus == null
      ? null
      : focus.kind === 'family'
        ? focus.id
        : (patients?.find((p) => p.id === focus.id)?.family_id ?? null)
  useEffect(() => {
    if (focusedFamilyId != null) setExpanded((prev) => new Set(prev).add(focusedFamilyId))
  }, [focusedFamilyId, focus])

  if (familiesQuery.isError || patientsQuery.isError || segregationQuery.isError) {
    return (
      <p className="text-sm text-destructive">
        {apiErrorMessage(
          familiesQuery.error ?? patientsQuery.error ?? segregationQuery.error,
          'Failed to load families',
        )}
      </p>
    )
  }

  if (!families || !patients || !segregation) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  const byFamily = new Map<number, PatientResp[]>()
  for (const patient of patients) {
    byFamily.set(patient.family_id, [...(byFamily.get(patient.family_id) ?? []), patient])
  }
  const segByFamily = new Map(segregation.map((s) => [s.family_id, s]))

  const multi = families.filter((f) => (byFamily.get(f.id)?.length ?? 0) > 1)
  const singles = families.filter((f) => (byFamily.get(f.id)?.length ?? 0) === 1).length

  if (multi.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyTitle>No multi-member families</EmptyTitle>
          <EmptyDescription>
            Family structure and segregation only apply to families with more than one extracted patient
            {singles > 0 ? `; this paper has ${singles} single-patient ${singles === 1 ? 'family' : 'families'}.` : '.'}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead className="w-8" />
            <TableHead>Family</TableHead>
            <TableHead>Members</TableHead>
            <TableHead>Affected</TableHead>
            <TableHead>Unaffected</TableHead>
            <TableHead>Unknown</TableHead>
            <TableHead>Consanguineous</TableHead>
            <TableHead>Segregation criteria</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {multi.map((family) => (
            <FamilyRow
              key={family.id}
              paperId={paperId}
              family={family}
              members={byFamily.get(family.id) ?? []}
              seg={segByFamily.get(family.id)}
              flags={flags}
              expanded={expanded.has(family.id)}
              onToggle={() => toggle(family.id)}
              focus={focus}
            />
          ))}
        </TableBody>
      </Table>
      {singles > 0 && (
        <p className="text-xs text-muted-foreground">
          {singles} single-patient {singles === 1 ? 'family is' : 'families are'} not shown: there is no structure or
          segregation to display.
        </p>
      )}
    </div>
  )
}
