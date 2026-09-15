"""Timestamps leave the API saying which timezone they are in."""

import datetime

from lib.models.datetimes import _assume_utc
from lib.tasks.models import TaskResp, TaskStatus, TaskType


def _task(**kwargs):
    return TaskResp(
        id=1,
        paper_id=1,
        type=TaskType.PDF_PARSING,
        status=TaskStatus.RUNNING,
        tries=1,
        skip_successors=False,
        error_message=None,
        additional_context=None,
        family_id=None,
        patient_id=None,
        variant_id=None,
        phenotype_id=None,
        patient_variant_occurrence_id=None,
        updated_at=datetime.datetime(2026, 9, 13, 22, 42, 35),
        **kwargs,
    )


def test_a_naive_timestamp_is_serialised_as_utc():
    """SQLite drops the offset, so what the ORM hands back is naive -- but it is
    UTC, and the response has to say so. Without this the React app's
    `new Date()` read it as local time, which on UTC-4 put every timestamp four
    hours in the future and made a progress bar's elapsed time negative."""
    payload = _task().model_dump_json()

    assert '2026-09-13T22:42:35Z' in payload


def test_an_already_aware_timestamp_is_left_alone():
    """Anything arriving with an offset came from somewhere that knew."""
    aware = datetime.datetime(
        2026, 9, 13, 18, 42, 35, tzinfo=datetime.timezone(-datetime.timedelta(hours=4))
    )

    assert _assume_utc(aware) is aware


def test_none_stays_none():
    assert _task(started_at=None).started_at is None
