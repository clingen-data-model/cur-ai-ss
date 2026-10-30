/* All patient fields, editable -- the SPA analog of lib/ui/paper/patients.py's
 * render_patient(), minus the family/consanguinity/segregation-analysis and
 * phenotypes sections (out of scope for the Occurrences page for now).
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { updatePatientPapersPaperIdPatientsPatientIdPatch } from '@/api/generated'
import {
  AffectedStatus,
  AgeUnit,
  CountryCode,
  Ethnicity,
  OnsetCategory,
  ProbandStatus,
  Race,
  RelationshipToProband,
  SexAtBirth,
  TaskType,
  TwinType,
} from '@/api/generated/types.gen'
import type { PatientResp, PatientUpdateRequest } from '@/api/generated/types.gen'
import { EditableAgeRow, EditableSelectRow, EditableSwitchRow, EditableTextRow } from '@/components/EditableField'
import { PhenotypesTable } from '@/components/PhenotypesTable'
import { ScopedRerunButton } from '@/components/ScopedRerunButton'
import { apiErrorMessage } from '@/lib/apiError'

export function PatientDetailPanel({ paperId, patient }: { paperId: number; patient: PatientResp }) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationKey: ['paper-edit', paperId],
    mutationFn: (body: PatientUpdateRequest) =>
      updatePatientPapersPaperIdPatientsPatientIdPatch({
        path: { paper_id: paperId, patient_id: patient.id },
        body,
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['patients', paperId] })
      // Editing a patient sets updated_by_user_id, which backs the papers
      // table's touched_by filter -- without this, "worked on by" stays
      // stale until the 5-minute staleTime lapses on its own.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to save patient')),
  })

  const save = (body: PatientUpdateRequest) => mutation.mutate(body)

  return (
    <div className="p-4 bg-muted/30">
      <div className="flex items-center justify-between mb-2 max-w-xl">
        <h4 className="text-sm font-semibold">Patient</h4>
        <ScopedRerunButton
          paperId={paperId}
          taskType={TaskType.PATIENT_DEMOGRAPHICS}
          scope={{ patient_id: patient.id }}
          label="Re-run demographics"
          description="Re-runs demographics for this patient only -- sex, ages, ancestry, affected status, carrier status and relationship to the proband -- overwriting the fields below. Then re-runs this patient's phenotype extraction and the paper's patient-variant links."
        />
      </div>
      <div className="max-w-xl">
        <EditableTextRow
          label="Identifier"
          value={patient.identifier}
          evidence={patient.identifier_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ identifier: value, identifier_human_edit_note: note })
          }
        />
        <EditableSelectRow
          label="Proband Status"
          value={patient.proband_status}
          options={Object.values(ProbandStatus)}
          evidence={patient.proband_status_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ proband_status: value, proband_status_human_edit_note: note })
          }
        />
        <EditableSelectRow
          label="Affected Status"
          value={patient.affected_status}
          options={Object.values(AffectedStatus)}
          evidence={patient.affected_status_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ affected_status: value, affected_status_human_edit_note: note })
          }
        />
        <EditableSelectRow
          label="Sex at Birth"
          value={patient.sex}
          options={Object.values(SexAtBirth)}
          evidence={patient.sex_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) => save({ sex: value, sex_human_edit_note: note })}
        />
        <EditableAgeRow
          label="Age at Diagnosis"
          value={patient.age_diagnosis}
          unit={patient.age_diagnosis_unit ?? null}
          unitOptions={Object.values(AgeUnit)}
          evidence={patient.age_diagnosis_evidence}
          isSaving={mutation.isPending}
          onSaveValue={(value, note) =>
            save({ age_diagnosis: value, age_diagnosis_human_edit_note: note })
          }
          onSaveUnit={(unit) => save({ age_diagnosis_unit: unit })}
        />
        <EditableAgeRow
          label="Age at Report"
          value={patient.age_report}
          unit={patient.age_report_unit ?? null}
          unitOptions={Object.values(AgeUnit)}
          evidence={patient.age_report_evidence}
          isSaving={mutation.isPending}
          onSaveValue={(value, note) =>
            save({ age_report: value, age_report_human_edit_note: note })
          }
          onSaveUnit={(unit) => save({ age_report_unit: unit })}
        />
        <EditableAgeRow
          label="Age at Death"
          value={patient.age_death}
          unit={patient.age_death_unit ?? null}
          unitOptions={Object.values(AgeUnit)}
          evidence={patient.age_death_evidence}
          isSaving={mutation.isPending}
          onSaveValue={(value, note) =>
            save({ age_death: value, age_death_human_edit_note: note })
          }
          onSaveUnit={(unit) => save({ age_death_unit: unit })}
        />
        <EditableAgeRow
          label="Age at Onset"
          value={patient.age_onset}
          unit={patient.age_onset_unit ?? null}
          unitOptions={Object.values(AgeUnit)}
          evidence={patient.age_onset_evidence}
          isSaving={mutation.isPending}
          onSaveValue={(value, note) =>
            save({ age_onset: value, age_onset_human_edit_note: note })
          }
          onSaveUnit={(unit) => save({ age_onset_unit: unit })}
        />
        <EditableSelectRow
          label="Onset"
          value={patient.onset_category}
          options={Object.values(OnsetCategory)}
          allowNone
          evidence={patient.onset_category_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ onset_category: value, onset_category_human_edit_note: note })
          }
        />
        <EditableSelectRow
          label="Country of Origin"
          value={patient.country_of_origin}
          options={Object.values(CountryCode)}
          evidence={patient.country_of_origin_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ country_of_origin: value, country_of_origin_human_edit_note: note })
          }
        />
        <EditableSelectRow
          label="Race"
          value={patient.race}
          options={Object.values(Race)}
          evidence={patient.race_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) => save({ race: value, race_human_edit_note: note })}
        />
        <EditableSelectRow
          label="Ethnicity"
          value={patient.ethnicity}
          options={Object.values(Ethnicity)}
          evidence={patient.ethnicity_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ ethnicity: value, ethnicity_human_edit_note: note })
          }
        />
        <EditableTextRow
          label="Ancestry"
          value={patient.ancestry ?? ''}
          evidence={patient.ancestry_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ ancestry: value.trim() || null, ancestry_human_edit_note: note })
          }
        />
        <EditableSwitchRow
          label="Is Obligate Carrier"
          value={patient.is_obligate_carrier ?? false}
          evidence={patient.is_obligate_carrier_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ is_obligate_carrier: value, is_obligate_carrier_human_edit_note: note })
          }
        />
        <EditableSelectRow
          label="Relationship to Proband"
          value={patient.relationship_to_proband}
          options={Object.values(RelationshipToProband)}
          allowNone
          evidence={patient.relationship_to_proband_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({
              relationship_to_proband: value,
              relationship_to_proband_human_edit_note: note,
            })
          }
        />
        <EditableSelectRow
          label="Twin Type"
          value={patient.twin_type}
          options={Object.values(TwinType)}
          allowNone
          evidence={patient.twin_type_evidence}
          isSaving={mutation.isPending}
          onSave={(value, note) =>
            save({ twin_type: value, twin_type_human_edit_note: note })
          }
        />
      </div>

      <div className="mt-4 border-t pt-4">
        <PhenotypesTable
          paperId={paperId}
          patientId={patient.id}
          affectedStatus={patient.affected_status}
        />
      </div>
    </div>
  )
}
