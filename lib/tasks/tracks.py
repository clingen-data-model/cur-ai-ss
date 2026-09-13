"""The pipeline's parallel tracks, as the progress bars group them.

Defined here rather than in the frontend because the wall-clock aggregate in
GET /stats has to group by the same thing the bars draw. Two copies of this
mapping would drift the first time a task type is added, and the symptom would
be a silently mis-scaled bar rather than an error -- so the grouping travels
with the statistics that depend on it.
"""

from lib.tasks.models import TaskType

# After Paper Classifier the pipeline forks into branches that run
# concurrently and rejoin at Patient Variant Occurrences, so these are parallel
# tracks rather than sequential phases. The cut is by subject, matching the
# entities the UI already names.
#
# GENERAL_PAPER_QUESTION is in no track: it is ad-hoc chat created by the
# router, not pipeline work, and counting it would make a paper look unfinished
# every time someone asked a question about it.
PIPELINE_TRACKS: list[tuple[str, str, list[TaskType]]] = [
    (
        'paper',
        'Paper',
        [
            TaskType.PDF_PARSING,
            TaskType.PAPER_CLASSIFIER,
            TaskType.PAPER_METADATA,
        ],
    ),
    (
        'patients',
        'Patients',
        [
            TaskType.PEDIGREE_DESCRIPTION,
            TaskType.PATIENT_EXTRACTION,
            TaskType.PATIENT_DEMOGRAPHICS,
            TaskType.PHENOTYPE_EXTRACTION,
            TaskType.HPO_LINKING,
        ],
    ),
    (
        'variants',
        'Variants',
        [
            TaskType.VARIANT_EXTRACTION,
            TaskType.VARIANT_HARMONIZATION,
            TaskType.VARIANT_ANNOTATION,
        ],
    ),
    (
        'analysis',
        'Analysis',
        [
            TaskType.PATIENT_VARIANT_OCCURRENCES,
            TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
            TaskType.SEGREGATION_ANALYSIS_COMPUTED,
            TaskType.COMPOUND_HET_EVALUATION,
            TaskType.MONDO_LINKING,
        ],
    ),
]

TRACK_OF_TYPE: dict[TaskType, str] = {
    task_type: track_id
    for track_id, _, task_types in PIPELINE_TRACKS
    for task_type in task_types
}
