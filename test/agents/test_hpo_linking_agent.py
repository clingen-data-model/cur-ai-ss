"""What the HPO linking agent is shown of a candidate term."""

from lib.agents import hpo_linking_agent
from lib.models import HpoCandidate


def test_candidate_terms_carry_the_definition_and_comment(monkeypatch) -> None:
    monkeypatch.setattr(
        hpo_linking_agent,
        'find_matching_hpo_terms',
        lambda text, limit: [
            HpoCandidate(id='HP:0000822', name='hypertension', similarity_score=90.0),
            HpoCandidate(id='HP:GONE', name='gone', similarity_score=40.0),
        ],
    )
    described = {
        'HP:0000822': {
            'definition': 'Chronic increased systemic arterial pressure.',
            'comment': 'Systolic BP of 140 mm Hg or higher.',
        }
    }
    monkeypatch.setattr(hpo_linking_agent, 'describe_term_id', described.get)

    assert hpo_linking_agent.candidate_terms('high blood pressure') == [
        {
            'id': 'HP:0000822',
            'name': 'hypertension',
            'similarity_score': 90.0,
            'definition': 'Chronic increased systemic arterial pressure.',
            'comment': 'Systolic BP of 140 mm Hg or higher.',
        },
        {
            'id': 'HP:GONE',
            'name': 'gone',
            'similarity_score': 40.0,
            'definition': None,
            'comment': None,
        },
    ]
