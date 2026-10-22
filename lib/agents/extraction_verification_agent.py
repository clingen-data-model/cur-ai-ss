"""The extraction verification agent: a pass over a paper's finished
extraction, run as the last task of its pipeline.

For now it does one thing: fold the flags that say the same thing into one.
Every extraction agent raises flags for its own scope and knows nothing of
the others, and the per-patient ones run concurrently, so one decision about
the paper is routinely flagged several times in different words (see
lib.models.flag). This agent reads the whole list once and groups the
repeats; lib.tasks.extraction_verification applies the result. It sees no
paper text: the subjects and reasonings are the whole input, and the
question is only whether two of them describe one decision.
"""

from agents import Agent

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.model_facing import model_facing_output
from lib.agents.model_factory import decision_model_settings, extraction_model
from lib.models.flag import FlagMergeOutput

EXTRACTION_VERIFICATION_AGENT_INSTRUCTIONS = """
You are given the open curator flags on one paper, as a JSON list. Each has
an id, the agent that raised it, its kind, what it is about (a patient,
family, variant or phenotype, or null), a subject and the basis behind
it. The agents ran separately -- one per patient, per family or per variant,
and at the same time -- so the same decision about the paper may appear more
than once, worded differently or about different people.

Return the groups of flags that are ONE decision raised more than once. A
curator should see each decision once, so the flags in a group will be
folded into the earliest of them.

Two flags are the same decision when a curator who settled one would have
settled the other with the same judgment, because they rest on the same
fact about the paper:
- the same inference applied to several people (a country, race or
  ethnicity taken from the study site or cohort description; a status read
  off the same pedigree feature);
- the same conflict or ambiguity in the paper noticed in several runs of
  one agent (a label that differs between the text and a figure; a proband
  the paper does not mark);
- the same person, variant or finding excluded for the same reason.

Two flags are NOT the same decision when they merely share a kind or a
shape:
- two variants each left unresolved, two phenotypes each without a term,
  two patients each with an ambiguous age -- separate rows, separate
  judgments, even if the sentence is the same;
- the same kind of decision resting on different facts (a country inferred
  for one patient from the study site and for another from a stated
  birthplace);
- flags about different people where the basis turns on something
  specific to each person.

Only flags of the same kind raised by the same agent can be one decision:
the system rejects a group that mixes kinds or agents, so a conflict and an
inference about the same fact stay separate.

Flags about different compound-het pairs in different people are kept apart
by the system whatever you return, so do not group them. Flags about the same
variant in different people, or the same person's several variants, can be
one decision when one statement in the paper explains them all.

When in doubt, leave the flags apart: a curator resolving two flags costs a
click, while a merged pair that should have stayed separate hides a
decision. Each group names the id to keep (the lowest), the ids it absorbs,
and one sentence saying what the shared decision is. A flag belongs to at
most one group, and a group has at least two flags. Return no groups when
nothing repeats.
"""

agent = Agent(
    name='extraction_verifier',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=extraction_model(),
    model_settings=decision_model_settings(),
    output_type=model_facing_output(FlagMergeOutput),
)
