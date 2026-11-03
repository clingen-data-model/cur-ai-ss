"""Curator sign-off (lib/models/signoff.py) and the review walk's cases
(lib/misc/review_cases.py)."""

import pytest

from lib.models import (
    FamilyDB,
    FlagDB,
    GeneDB,
    PaperDB,
    PatientDB,
    PatientVariantOccurrenceDB,
    PhenotypeDB,
    VariantDB,
)
from lib.models.paper import ReviewStatus
from lib.models.signoff import clear_signoff, stamp


def _ev(value=None):
    block = {'value': value, 'reasoning': 'test'}
    if value is not None:
        block['citations'] = [{'anchor': 'paragraph-1', 'quote': 'test'}]
    return block


def _patient_fields(identifier, **overrides):
    fields = dict(
        proband_status='Unknown',
        sex='Unknown',
        country_of_origin='Unknown',
        race='Unknown',
        ethnicity='Unknown',
        affected_status='Unknown',
    )
    fields.update(overrides)
    evidence = {f'{k}_evidence': _ev(v) for k, v in fields.items()}
    evidence['identifier_evidence'] = _ev(identifier)
    evidence['age_diagnosis_evidence'] = _ev()
    evidence['age_report_evidence'] = _ev()
    evidence['age_death_evidence'] = _ev()
    evidence['family_assignment_evidence'] = _ev('F')
    return {**fields, **evidence}


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(content_hash='abc', gene_id=gene.id, filename='t.pdf')
    db_session.add(paper)
    db_session.flush()
    return paper


def _family(db_session, paper, identifier):
    family = FamilyDB(
        paper_id=paper.id,
        identifier=identifier,
        identifier_evidence=_ev(identifier),
        consanguinity=False,
        consanguinity_evidence=_ev(False),
    )
    db_session.add(family)
    db_session.flush()
    return family


def _patient(db_session, paper, family, identifier, **overrides):
    patient = PatientDB(
        paper_id=paper.id,
        family_id=family.id,
        identifier=identifier,
        **_patient_fields(identifier, **overrides),
    )
    db_session.add(patient)
    db_session.flush()
    return patient


def _variant(db_session, paper, text):
    evidence_fields = (
        'transcript',
        'protein_accession',
        'genomic_accession',
        'lrg_accession',
        'gene_accession',
        'genomic_coordinates',
        'genome_build',
        'rsid',
        'caid',
        'hgvs_c',
        'hgvs_p',
        'hgvs_g',
    )
    variant = VariantDB(
        paper_id=paper.id,
        variant=text,
        variant_type='Missense',
        functional_evidence=False,
        main_focus=False,
        variant_evidence=_ev(text),
        variant_type_evidence=_ev('Missense'),
        functional_evidence_evidence=_ev(False),
        main_focus_evidence=_ev(False),
        **{f'{f}_evidence': _ev() for f in evidence_fields},
    )
    db_session.add(variant)
    db_session.flush()
    return variant


def _occurrence(db_session, paper, patient, variant):
    occurrence = PatientVariantOccurrenceDB(
        paper_id=paper.id,
        patient_id=patient.id,
        variant_id=variant.id,
        zygosity='Heterozygous',
        zygosity_evidence=_ev('Heterozygous'),
        inheritance='Dominant',
        inheritance_evidence=_ev('Dominant'),
        variant_inheritance='Unknown',
        variant_inheritance_evidence=_ev('Unknown'),
        testing_methods=['Sanger Sequencing'],
        testing_methods_evidence=[_ev('Sanger Sequencing')],
    )
    db_session.add(occurrence)
    db_session.flush()
    return occurrence


def _flag(db_session, paper, subject, **links):
    flag = FlagDB(
        paper_id=paper.id,
        source='PATIENT_EXTRACTION',
        kind='excluded',
        subject=subject,
        evidence={'value': subject, 'reasoning': 'test', 'citations': []},
        **links,
    )
    db_session.add(flag)
    db_session.flush()
    return flag


@pytest.fixture
def case(db_session, paper):
    """One family: a proband with one occurrence of one variant, and an
    unaffected relative with none."""
    family = _family(db_session, paper, 'Family 1')
    proband = _patient(
        db_session,
        paper,
        family,
        'II-1',
        proband_status='Proband',
        affected_status='Affected',
    )
    relative = _patient(db_session, paper, family, 'I-1', affected_status='Unaffected')
    variant = _variant(db_session, paper, 'c.1A>G')
    occurrence = _occurrence(db_session, paper, proband, variant)
    db_session.commit()
    return dict(
        family=family,
        proband=proband,
        relative=relative,
        variant=variant,
        occurrence=occurrence,
    )


def test_signoff_stamps_occurrences_and_reports_progress(
    client, db_session, paper, case, test_user
):
    # A second occurrence, left unstamped, so the paper stays incomplete.
    other = _occurrence(db_session, paper, case['relative'], case['variant'])
    db_session.commit()
    resp = client.post(
        f'/papers/{paper.id}/signoff', json={'occurrence_ids': [case['occurrence'].id]}
    )
    assert resp.status_code == 200
    assert resp.json() == {'total': 2, 'confirmed': 1}

    occurrences = {
        o['id']: o for o in client.get(f'/papers/{paper.id}/occurrences').json()
    }
    stamped = occurrences[case['occurrence'].id]
    assert stamped['reviewed_at'] is not None
    assert stamped['reviewed_by']['id'] == test_user.id
    assert occurrences[other.id]['reviewed_at'] is None
    # The stamp lives on the occurrence alone.
    patient = client.get(f'/papers/{paper.id}/patients').json()[0]
    assert 'reviewed_at' not in patient

    # The paper and the list carry the same progress.
    assert client.get(f'/papers/{paper.id}').json()['signoff'] == {
        'total': 2,
        'confirmed': 1,
    }
    listed = next(p for p in client.get('/papers').json() if p['id'] == paper.id)
    assert listed['signoff'] == {'total': 2, 'confirmed': 1}
    # The first stamp starts the review, under whoever stamped.
    assert listed['review_status'] == 'in_progress'
    assert listed['review_assignee']['id'] == test_user.id


def test_signoff_can_be_taken_back_and_the_review_reopens(
    client, db_session, paper, case, test_user
):
    url = f'/papers/{paper.id}/signoff'
    other = _occurrence(db_session, paper, case['relative'], case['variant'])
    db_session.commit()
    resp = client.post(url, json={'occurrence_ids': [case['occurrence'].id, other.id]})
    assert resp.json()['confirmed'] == 2
    assert client.get(f'/papers/{paper.id}').json()['review_status'] == 'completed'

    resp = client.post(
        url, json={'occurrence_ids': [case['occurrence'].id], 'confirmed': False}
    )
    assert resp.json()['confirmed'] == 1
    occurrences = {
        o['id']: o for o in client.get(f'/papers/{paper.id}/occurrences').json()
    }
    assert occurrences[case['occurrence'].id]['reviewed_at'] is None
    assert occurrences[case['occurrence'].id]['reviewed_by'] is None
    body = client.get(f'/papers/{paper.id}').json()
    assert body['review_status'] == 'in_progress'
    # The assignee stays: the paper is still theirs to finish.
    assert body['review_assignee']['id'] == test_user.id

    # Taking the last one back leaves it in progress, not unassigned.
    resp = client.post(url, json={'occurrence_ids': [other.id], 'confirmed': False})
    assert resp.json()['confirmed'] == 0
    assert client.get(f'/papers/{paper.id}').json()['review_status'] == 'in_progress'


def test_signoff_refuses_an_occurrence_of_another_paper_and_stamps_nothing(
    client, db_session, paper, case
):
    other = PaperDB(content_hash='other', gene_id=paper.gene_id, filename='o.pdf')
    db_session.add(other)
    db_session.flush()
    resp = client.post(
        f'/papers/{other.id}/signoff', json={'occurrence_ids': [case['occurrence'].id]}
    )
    assert resp.status_code == 404
    assert 'Occurrences not found' in resp.json()['detail']
    assert client.get(f'/papers/{paper.id}').json()['signoff']['confirmed'] == 0


def test_review_completes_itself_once_every_occurrence_is_stamped(
    client, db_session, paper, case, test_user
):
    # An open flag is advice, not a gate.
    _flag(db_session, paper, 'untested sibling', patient_id=case['proband'].id)
    other = _occurrence(db_session, paper, case['relative'], case['variant'])
    db_session.commit()
    resp = client.post(
        f'/papers/{paper.id}/signoff', json={'occurrence_ids': [case['occurrence'].id]}
    )
    assert resp.json() == {'total': 2, 'confirmed': 1}
    assert client.get(f'/papers/{paper.id}').json()['review_status'] == 'in_progress'

    resp = client.post(
        f'/papers/{paper.id}/signoff', json={'occurrence_ids': [other.id]}
    )
    assert resp.json() == {'total': 2, 'confirmed': 2}
    body = client.get(f'/papers/{paper.id}').json()
    assert body['review_status'] == 'completed'
    # Nobody was assigned, so the curator who finished is.
    assert body['review_assignee']['id'] == test_user.id


def test_an_agent_rewrite_unstamps_the_occurrence_and_reopens_a_completed_review(
    db_session, paper, case, test_user
):
    stamp(case['occurrence'], test_user)
    paper.review_status = ReviewStatus.COMPLETED
    paper.review_assignee_user_id = test_user.id
    db_session.flush()

    clear_signoff(db_session, paper.id, [None])
    # Nothing was stamped there: no change.
    assert paper.review_status == ReviewStatus.COMPLETED

    clear_signoff(db_session, paper.id, [case['occurrence']])
    assert case['occurrence'].reviewed_at is None
    assert case['occurrence'].reviewed_by_user_id is None
    assert paper.review_status == ReviewStatus.IN_PROGRESS
    assert paper.review_assignee_user_id == test_user.id


def test_review_cases_are_the_families_in_order_with_their_flags(
    client, db_session, paper, case, test_user
):
    family2 = _family(db_session, paper, 'Family 2')
    lone = _patient(db_session, paper, family2, 'P1', affected_status='Affected')
    variant2 = _variant(db_session, paper, 'c.2A>G')
    linked = _occurrence(db_session, paper, lone, variant2)
    # A phenotype flag reaches its patient's family.
    phenotype = PhenotypeDB(
        paper_id=paper.id,
        patient_id=lone.id,
        concept='seizures',
        concept_evidence=_ev('seizures'),
    )
    db_session.add(phenotype)
    db_session.flush()
    # A family nothing links to has nothing to stamp.
    family3 = _family(db_session, paper, 'Family 3')
    _patient(db_session, paper, family3, 'P2')
    unlinked = _variant(db_session, paper, 'c.3A>G')
    about_relative = _flag(
        db_session, paper, 'about I-1', patient_id=case['relative'].id
    )
    about_phenotype = _flag(
        db_session, paper, 'about seizures', phenotype_id=phenotype.id
    )
    about_family2 = _flag(db_session, paper, 'about F2', family_id=family2.id)
    about_paper = _flag(db_session, paper, 'about nobody')
    about_unlinked = _flag(db_session, paper, 'about c.3A>G', variant_id=unlinked.id)
    resolved = _flag(db_session, paper, 'settled', patient_id=case['proband'].id)
    db_session.commit()
    resp = client.post(f'/papers/{paper.id}/flags/{resolved.id}/resolve', json={})
    assert resp.status_code == 200

    resp = client.get(f'/papers/{paper.id}/review-cases')
    assert resp.status_code == 200
    cases = resp.json()
    assert [c['key'] for c in cases] == [
        f'family-{case["family"].id}',
        f'family-{family2.id}',
        f'family-{family3.id}',
        'variants',
        'paper',
    ]
    first, second, third, variants, paper_case = cases

    assert first['kind'] == 'family'
    assert first['label'] == 'Family 1'
    assert first['family_id'] == case['family'].id
    assert first['patient_ids'] == [case['proband'].id, case['relative'].id]
    assert first['occurrence_ids'] == [case['occurrence'].id]
    assert first['variant_ids'] == [case['variant'].id]
    assert first['family_ids'] == [case['family'].id]
    # The resolved flag is not listed.
    assert first['flag_ids'] == [about_relative.id]
    assert first['confirmed'] is False
    assert first['optional'] is False

    assert second['label'] == 'Family 2'
    assert second['patient_ids'] == [lone.id]
    assert second['occurrence_ids'] == [linked.id]
    assert second['variant_ids'] == [variant2.id]
    assert second['flag_ids'] == [about_phenotype.id, about_family2.id]

    assert third['occurrence_ids'] == []
    assert third['confirmed'] is True

    assert variants['kind'] == 'unlinked_variants'
    assert variants['variant_ids'] == [unlinked.id]
    assert variants['flag_ids'] == [about_unlinked.id]
    assert variants['confirmed'] is False
    assert variants['optional'] is True
    assert paper_case['kind'] == 'paper'
    assert paper_case['flag_ids'] == [about_paper.id]
    assert paper_case['confirmed'] is False
    assert paper_case['optional'] is True


def test_review_case_is_confirmed_once_every_occurrence_is_stamped(
    client, db_session, paper, case, test_user
):
    other = _occurrence(db_session, paper, case['relative'], case['variant'])
    stamp(case['occurrence'], test_user)
    db_session.commit()
    (only,) = client.get(f'/papers/{paper.id}/review-cases').json()
    assert only['confirmed'] is False

    stamp(other, test_user)
    db_session.commit()
    (only,) = client.get(f'/papers/{paper.id}/review-cases').json()
    assert only['confirmed'] is True
