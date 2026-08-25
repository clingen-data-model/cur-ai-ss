"""Which model each agent runs on.

Two tiers. The reading passes send a whole PDF and have to resolve sideways
tables and figures, so they run on the capable model. The ontology and
normalization lookups never see the paper -- they are handed a phenotype
string, a disease name or an HGVS expression and match it against a reference,
largely through tool calls -- so they run on the cheap one. There are roughly
fifty of those per paper against five reading passes, which is where the bill
actually is.
"""

from typing import Any

from lib.agents.hpo_linking_agent import agent as hpo_agent
from lib.agents.mondo_linking_agent import agent as mondo_agent
from lib.agents.paper_extraction import _shared
from lib.agents.variant_harmonization_agent import agent as harmonization_agent
from lib.core.environment import env


def test_the_lookups_run_on_the_cheap_tier():
    for agent in (hpo_agent, harmonization_agent):
        assert agent.model == env.OPENAI_LINKING_MODEL


def test_mondo_linking_stays_on_the_capable_tier():
    """It is named a linking task but sends the whole paper as context, to
    judge which disease the authors mean. On the cheap tier it returned no
    match for a paper where the capable one at least found an ancestor term."""
    assert mondo_agent.model == env.OPENAI_API_DEPLOYMENT


def test_the_two_tiers_are_actually_different_models():
    """Pointing both at one model would pass every other test here silently."""
    assert env.OPENAI_LINKING_MODEL != env.OPENAI_API_DEPLOYMENT


def test_a_reading_pass_runs_on_the_capable_tier(monkeypatch):
    """The passes read the PDF itself, so they follow the main deployment."""
    sent: dict[str, Any] = {}

    class FakeCompletions:
        def parse(self, **kwargs: Any) -> Any:
            sent.update(kwargs)
            raise _Stop

    class FakeClient:
        chat = type('chat', (), {'completions': FakeCompletions()})()

    monkeypatch.setattr(_shared, '_client', lambda: FakeClient())

    try:
        _shared._run('label', 1, _Schema, 'instructions', [])
    except _Stop:
        pass

    assert sent['model'] == env.OPENAI_API_DEPLOYMENT


class _Stop(Exception):
    """Raised to stop _run once the request has been captured."""


class _Schema:
    pass
