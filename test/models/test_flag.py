"""ExtractionFlag in the patient extraction output and its conversion to a row."""

import pytest
from pydantic import ValidationError

from lib.models import FlagDB
from lib.models.converters import flag_to_db
from lib.models.flag import ExtractionFlag
from lib.models.patient import (
    FamilyEntry,
    PatientExtractionOutput,
    PatientIdentity,
    ProbandStatus,
)

_CITE = [{'anchor': 'paragraph-3', 'quote': 'her sister was not tested'}]


def _block(value: object, reasoning: str = 'because') -> dict:
    return {'value': value, 'reasoning': reasoning, 'citations': _CITE}


def _output(flags: list[dict]) -> PatientExtractionOutput:
    return PatientExtractionOutput(
        patients=[
            PatientIdentity(
                identifier=_block('Patient 1'),
                family_identifier=_block('Family 1'),
                proband_status=_block(ProbandStatus.Proband),
            )
        ],
        families=[
            FamilyEntry(
                family={
                    'identifier': _block('Family 1'),
                    'consanguinity': _block(False),
                },
                patient_identifiers=[_block('Patient 1')],
            )
        ],
        flags=flags,
    )


def test_flags_default_to_empty_so_an_older_output_still_loads():
    assert _output([]).flags == []


def test_a_flag_may_name_an_extracted_patient_or_nothing():
    out = _output(
        [
            {'patient_identifier': 'Patient 1', 'flag': _block('chosen as proband')},
            {'patient_identifier': None, 'flag': _block('untested sister')},
        ]
    )
    assert [f.patient_identifier for f in out.flags] == ['Patient 1', None]


def test_a_flag_about_an_unknown_patient_is_rejected():
    with pytest.raises(ValidationError, match='Flags reference non-existent'):
        _output([{'patient_identifier': 'Patient 9', 'flag': _block('x')}])


def test_a_flag_needs_a_citation_like_every_other_evidence_block():
    with pytest.raises(ValidationError):
        ExtractionFlag(
            patient_identifier=None,
            flag={'value': 'untested sister', 'reasoning': 'no source'},
        )


def test_flag_to_db_keeps_the_whole_block_as_evidence():
    flag = ExtractionFlag(patient_identifier=None, flag=_block('untested sister'))
    row = flag_to_db(7, flag, source='PATIENT_EXTRACTION', patient_id=None)
    assert isinstance(row, FlagDB)
    assert (row.paper_id, row.patient_id, row.source) == (
        7,
        None,
        'PATIENT_EXTRACTION',
    )
    assert row.subject == 'untested sister'
    assert row.evidence['reasoning'] == 'because'
    assert row.evidence['citations'][0]['anchor'] == 'paragraph-3'
    assert row.resolved_by_user_id is None and row.resolved_at is None
