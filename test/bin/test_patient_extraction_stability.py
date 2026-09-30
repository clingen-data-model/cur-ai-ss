"""The run comparison behind lib/bin/patient_extraction_stability.py."""

from lib.bin.patient_extraction_stability import compare_runs


def test_identical_runs_are_stable():
    report = compare_runs([{'II-1', 'II-2'}, {'II-1', 'II-2'}, {'II-2', 'II-1'}])

    assert report.stable
    assert report.dissenting_runs == []
    assert report.union == report.intersection == {'II-1', 'II-2'}


def test_one_dissenting_run_is_named():
    report = compare_runs([{'II-1', 'II-2'}, {'II-1'}, {'II-1', 'II-2'}])

    assert not report.stable
    assert report.dissenting_runs == [1]
    assert report.union == {'II-1', 'II-2'}
    assert report.intersection == {'II-1'}


def test_all_different_runs_all_dissent():
    report = compare_runs([{'a'}, {'b'}, {'c'}])

    assert not report.stable
    assert report.dissenting_runs == [0, 1, 2]
    assert report.union == {'a', 'b', 'c'}
    assert report.intersection == set()


def test_no_runs_or_one_run_is_trivially_stable():
    assert compare_runs([]).stable
    assert compare_runs([{'a'}]).stable
