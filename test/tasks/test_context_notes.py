import pytest

from lib.models import (
    FamilyDB,
    FlagDB,
    GeneDB,
    PaperContextNoteDB,
    PaperDB,
    PatientDB,
)
from lib.models.paper_context_note import ContextNoteSource
from lib.tasks.context_notes import (
    add_context_note,
    anchor_for,
    flag_scope_label,
    render_context_notes,
    scope_label,
)


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='GCK')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(content_hash='notes', gene_id=gene.id, filename='gck.pdf')
    db_session.add(paper)
    db_session.flush()
    return paper


def _patient(db_session, paper, identifier):
    family = FamilyDB(
        paper_id=paper.id,
        identifier='Family A',
        identifier_evidence={'value': 'Family A', 'reasoning': 't'},
        consanguinity=False,
        consanguinity_evidence={'value': False, 'reasoning': 't'},
    )
    db_session.add(family)
    db_session.flush()
    patient = PatientDB(
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
        family_assignment_evidence={'value': 'Family A', 'reasoning': 't'},
    )
    db_session.add(patient)
    db_session.flush()
    return patient


def test_scope_label_names_the_rows_a_run_is_for(db_session, paper):
    patient = _patient(db_session, paper, 'P85')

    assert scope_label(db_session) is None
    assert scope_label(db_session, patient_id=patient.id) == 'patient P85'
    # A row that no longer exists is left out rather than failing the run.
    assert scope_label(db_session, patient_id=patient.id + 1000) is None


def test_anchor_for_joins_step_row_and_flag(db_session, paper):
    patient = _patient(db_session, paper, 'P85')
    flag = FlagDB(
        paper_id=paper.id,
        patient_id=patient.id,
        source='PATIENT_DEMOGRAPHICS',
        kind='inferred',
        subject='country inferred from study site',
        evidence={'value': 'x', 'reasoning': 'r', 'citations': []},
    )
    db_session.add(flag)
    db_session.flush()

    assert anchor_for('HPO Linking') == 'HPO Linking'
    assert (
        anchor_for('HPO Linking', 'phenotype Seizures')
        == 'HPO Linking · phenotype Seizures'
    )
    assert anchor_for('Patient Demographics', flag_scope_label(flag), flag) == (
        'Patient Demographics · patient P85 · flag "country inferred from study site"'
    )


def test_add_context_note_skips_blank_and_replaces_a_flags_earlier_note(
    db_session, paper
):
    assert (
        add_context_note(db_session, paper.id, '  ', source=ContextNoteSource.CURATOR)
        is None
    )
    assert (
        add_context_note(db_session, paper.id, None, source=ContextNoteSource.CURATOR)
        is None
    )

    flag = FlagDB(
        paper_id=paper.id,
        source='PATIENT_DEMOGRAPHICS',
        kind='inferred',
        subject='s',
        evidence={'value': 'x', 'reasoning': 'r', 'citations': []},
    )
    db_session.add(flag)
    db_session.flush()
    add_context_note(db_session, paper.id, 'first', source=ContextNoteSource.CURATOR)
    add_context_note(
        db_session, paper.id, 'old', source=ContextNoteSource.FLAG, flag_id=flag.id
    )
    add_context_note(
        db_session, paper.id, ' new ', source=ContextNoteSource.FLAG, flag_id=flag.id
    )

    notes = db_session.query(PaperContextNoteDB).order_by(PaperContextNoteDB.id).all()
    assert [(n.text, n.source, n.flag_id) for n in notes] == [
        ('first', 'curator', None),
        ('new', 'flag', flag.id),
    ]


def test_render_context_notes_numbers_and_labels():
    assert render_context_notes([]) is None
    notes = [
        PaperContextNoteDB(text='Use Brazil.', source='curator'),
        PaperContextNoteDB(text='Febrile.', source='chat', anchor='HPO Linking'),
    ]
    assert render_context_notes(notes) == (
        '1. [All tasks] Use Brazil.\n\n2. [HPO Linking] Febrile.'
    )
