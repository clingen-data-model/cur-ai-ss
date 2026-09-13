"""The pipeline's parallel tracks, as the progress bars group them.

Defined here rather than in the frontend because the wall-clock aggregate in
GET /stats has to group by the same thing the bars draw. Two copies of this
mapping would drift the first time a task type is added, and the symptom would
be a silently mis-scaled bar rather than an error -- so the grouping travels
with the statistics that depend on it.
"""

from typing import NamedTuple

from lib.tasks.models import TaskType


class PipelineTrack(NamedTuple):
    id: str
    label: str
    task_types: list[TaskType]
    # Where this track sits in the pipeline's ordering, read off TASK_SUCCESSORS.
    # Tracks sharing a stage genuinely overlap in time; a later stage waits on an
    # earlier one. See STAGES below for why an estimate needs this.
    stage: int


# After Paper Classifier the pipeline forks into branches that run
# concurrently and rejoin at Patient Variant Occurrences, so these are parallel
# tracks rather than sequential phases. The cut is by subject, matching the
# entities the UI already names.
#
# GENERAL_PAPER_QUESTION is in no track: it is ad-hoc chat created by the
# router, not pipeline work, and counting it would make a paper look unfinished
# every time someone asked a question about it.
# STAGES. The four tracks are not all concurrent, and treating them as though
# they were is what made "time left" wrong in both directions.
#
# Reading TASK_SUCCESSORS: nothing starts until PDF Parsing and Paper Classifier
# have run, and Patients and Variants both hang off the classifier -- so Paper
# comes first and those two fork from it. Analysis begins at Patient Variant
# Occurrences, which waits on Patient Demographics *and* Variant Extraction, so
# it joins after both.
#
#     Paper -> { Patients || Variants } -> Analysis
#
# An estimate therefore adds the stages and takes the longest track within each,
# rather than the longest track overall (which ignores that three of them queue
# behind each other) or the sum of all four (which ignores the fork).
PIPELINE_TRACKS: list[PipelineTrack] = [
    PipelineTrack(
        'paper',
        'Paper',
        [
            TaskType.PDF_PARSING,
            TaskType.PAPER_CLASSIFIER,
            TaskType.PAPER_METADATA,
        ],
        stage=0,
    ),
    PipelineTrack(
        'patients',
        'Patients',
        [
            TaskType.PEDIGREE_DESCRIPTION,
            TaskType.PATIENT_EXTRACTION,
            TaskType.PATIENT_DEMOGRAPHICS,
            TaskType.PHENOTYPE_EXTRACTION,
            TaskType.HPO_LINKING,
        ],
        stage=1,
    ),
    PipelineTrack(
        'variants',
        'Variants',
        [
            TaskType.VARIANT_EXTRACTION,
            TaskType.VARIANT_HARMONIZATION,
            TaskType.VARIANT_ANNOTATION,
        ],
        stage=1,
    ),
    PipelineTrack(
        'analysis',
        'Analysis',
        [
            TaskType.PATIENT_VARIANT_OCCURRENCES,
            TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
            TaskType.SEGREGATION_ANALYSIS_COMPUTED,
            TaskType.COMPOUND_HET_EVALUATION,
            TaskType.MONDO_LINKING,
        ],
        stage=2,
    ),
]

TRACK_OF_TYPE: dict[TaskType, str] = {
    task_type: track.id for track in PIPELINE_TRACKS for task_type in track.task_types
}
