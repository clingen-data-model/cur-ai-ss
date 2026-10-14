"""ExtractionFlag in agent outputs and replace_flags, the shared persistence."""

import pytest
from pydantic import ValidationError

from lib.models import FamilyDB, FlagDB, GeneDB, PaperDB, PatientDB
from lib.models.flag import ExtractionFlag
from lib.models.patient import PatientExtractionOutput
from lib.models.phenotype import PhenotypeExtractionOutput
from lib.models.variant import VariantExtractionOutput
from lib.tasks.flags import match_label, replace_flags

_CITE = [{'anchor': 'paragraph-3', 'quote': 'her sister was not tested'}]


def _flag(subject: str, about: str | None = None) -> ExtractionFlag:
    return ExtractionFlag(
        about=about,
        flag={'value': subject, 'reasoning': 'because', 'citations': _CITE},
    )


@pytest.mark.parametrize(
    'model',
    [PatientExtractionOutput, VariantExtractionOutput, PhenotypeExtractionOutput],
)
def test_flags_default_to_empty_so_an_older_output_still_loads(model):
    field = 'patients' if model is PatientExtractionOutput else None
    kwargs = (
        {'patients': [], 'families': []}
        if field
        else {'variants': []}
        if model is VariantExtractionOutput
        else {'phenotypes': []}
    )
    assert model(**kwargs).flags == []


def test_a_flag_needs_a_citation_like_every_other_evidence_block():
    with pytest.raises(ValidationError):
        ExtractionFlag(about=None, flag={'value': 'x', 'reasoning': 'no source'})


def test_match_label_ignores_case_and_spacing_but_not_content():
    labels = [('Patient 1', 11), ('c.123A>G', 12), (None, 13)]
    assert match_label('patient  1', labels) == 11
    assert match_label('C.123a>g', labels) == 12
    assert match_label('Patient 2', labels) is None
    assert match_label('', labels) is None


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='TP53')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(content_hash='flags', gene_id=gene.id, filename='f.pdf')
    db_session.add(paper)
    db_session.flush()
    family = FamilyDB(
        paper_id=paper.id,
        identifier='Family 1',
        identifier_evidence={'value': 'Family 1', 'reasoning': 't'},
        consanguinity=False,
        consanguinity_evidence={'value': False, 'reasoning': 't'},
    )
    db_session.add(family)
    db_session.flush()
    patients = []
    for identifier in ('Patient 1', 'Patient 2'):
        p = PatientDB(
            paper_id=paper.id,
            family_id=family.id,
            identifier=identifier,
            identifier_evidence={'value': identifier, 'reasoning': 't'},
            proband_status='Unknown',
            proband_status_evidence={'value': 'Unknown', 'reasoning': 't'},
            sex='Unknown',
            sex_evidence={'value': 'Unknown', 'reasoning': 't'},
            age_diagnosis_evidence={'value': None, 'reasoning': 't'},
            age_report_evidence={'value': None, 'reasoning': 't'},
            age_death_evidence={'value': None, 'reasoning': 't'},
            country_of_origin='Unknown',
            country_of_origin_evidence={'value': 'Unknown', 'reasoning': 't'},
            race='Unknown',
            race_evidence={'value': 'Unknown', 'reasoning': 't'},
            ethnicity='Unknown',
            ethnicity_evidence={'value': 'Unknown', 'reasoning': 't'},
            affected_status='Unknown',
            affected_status_evidence={'value': 'Unknown', 'reasoning': 't'},
            family_assignment_evidence={'value': 'Family 1', 'reasoning': 't'},
        )
        db_session.add(p)
        patients.append(p)
    db_session.flush()
    return paper, family, patients


def test_replace_flags_resolves_about_and_keeps_an_unmatched_one(db_session, paper):
    paper_db, family, (p1, _) = paper
    labels = [(p1.identifier, p1.id)]

    def resolve(about: str) -> dict[str, int]:
        pid = match_label(about, labels)
        return {'patient_id': pid} if pid is not None else {}

    rows = replace_flags(
        db_session,
        paper_id=paper_db.id,
        source='PATIENT_EXTRACTION',
        flags=[
            _flag('chosen as proband', about='patient 1'),
            _flag('untested sister'),
            _flag('someone the output lost', about='Patient 9'),
        ],
        resolve=resolve,
    )
    db_session.flush()
    assert [(r.subject, r.patient_id) for r in rows] == [
        ('chosen as proband', p1.id),
        ('untested sister', None),
        ('someone the output lost', None),
    ]
    assert rows[0].evidence['citations'][0]['anchor'] == 'paragraph-3'
    assert rows[0].source == 'PATIENT_EXTRACTION'


def test_replace_flags_scope_bounds_the_delete_and_stamps_new_rows(db_session, paper):
    paper_db, family, (p1, p2) = paper
    for p in (p1, p2):
        replace_flags(
            db_session,
            paper_id=paper_db.id,
            source='PHENOTYPE_EXTRACTION',
            flags=[_flag(f'about {p.identifier}')],
            scope={'patient_id': p.id},
        )
    replace_flags(
        db_session,
        paper_id=paper_db.id,
        source='PATIENT_EXTRACTION',
        flags=[_flag('paper level')],
    )
    db_session.flush()

    # Re-running phenotype extraction for p1 replaces p1's flags only.
    replace_flags(
        db_session,
        paper_id=paper_db.id,
        source='PHENOTYPE_EXTRACTION',
        flags=[_flag('p1 again, stamped with the scope')],
        scope={'patient_id': p1.id},
    )
    db_session.flush()
    rows = db_session.query(FlagDB).filter_by(paper_id=paper_db.id).order_by(FlagDB.id)
    assert [(r.subject, r.patient_id, r.source) for r in rows] == [
        ('about Patient 2', p2.id, 'PHENOTYPE_EXTRACTION'),
        ('paper level', None, 'PATIENT_EXTRACTION'),
        ('p1 again, stamped with the scope', p1.id, 'PHENOTYPE_EXTRACTION'),
    ]


def test_replace_flags_without_scope_replaces_all_of_that_source(db_session, paper):
    paper_db, *_ = paper
    replace_flags(
        db_session,
        paper_id=paper_db.id,
        source='VARIANT_EXTRACTION',
        flags=[_flag('a'), _flag('b')],
    )
    replace_flags(
        db_session,
        paper_id=paper_db.id,
        source='PATIENT_EXTRACTION',
        flags=[_flag('other agent')],
    )
    replace_flags(
        db_session, paper_id=paper_db.id, source='VARIANT_EXTRACTION', flags=[]
    )
    db_session.flush()
    rows = db_session.query(FlagDB).filter_by(paper_id=paper_db.id).all()
    assert [r.subject for r in rows] == ['other agent']
