"""The extraction verification agent: a pass over a paper's finished
extraction, run as the last task of its pipeline.

One call, two jobs, one prompt:

- Inconsistencies. The extraction agents each write their own scope and know
  nothing of the others' output, so values that should agree can differ: a
  statement about a group applied to some members and not others, one
  individual's links giving them two disease names, two fields of one row
  contradicting each other. The agent reads the extracted values with their
  basis and the text of the blocks they cite -- not the paper -- and names
  each row that is out of line; these become ``inconsistent`` flags.
- Repeated flags. The per-patient agents run concurrently, so one decision
  about the paper is routinely flagged several times in different words (see
  lib.models.flag). The agent groups the repeats.

lib.tasks.extraction_verification builds the input and applies both answers.
"""

from agents import Agent

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.model_facing import model_facing_output
from lib.agents.model_factory import decision_model_settings, extraction_model
from lib.models.flag import ExtractionVerificationOutput

EXTRACTION_VERIFICATION_AGENT_INSTRUCTIONS = """
You are verifying one paper's finished extraction. The extraction was
written by several agents, one per individual, per family, per variant or
per paper, running separately and at the same time. You do two things and
return both in one answer: find the extracted values that should agree and
do not (part 1), and find the flags that raise one decision more than once
(part 2). You do not have the paper.

PART 1: INCONSISTENCIES

"The extraction" is one paper's finished extraction as JSON: its families,
each individual in them with their values, and each individual's variants
with the values of that link. Every value carries the basis the extracting agent
gave for it and the ids of the blocks it cites; "cited_blocks" holds the text
of every cited block. You do not have the rest of the paper.

Find the places where values that should agree do not. Report only those: you are not re-checking
the paper, and a value that is merely uncertain is not an inconsistency.

What counts:
- One statement, several people. A cited block that states a value for a
  group (every proband, all affected members, the whole cohort, every member
  tested) gives it to everyone in that group. When some of the group carry
  the value cited to that block and another member of the group is missing
  it or carries a different one, with nothing in that member's own basis or
  citations explaining why, that member is out of line. Read the block to
  decide who it covers: a statement about the probands does not reach their
  relatives.
- One fact, several links. Disease name and inheritance mechanism describe
  the individual or the family, so one individual's variants carry the same
  disease name and mechanism, and one family's links the same mechanism,
  unless the basis gives a reason. Testing methods may differ between one
  individual's variants when the variants were found differently (a deletion
  by a copy-number method, a point change by sequencing); otherwise they
  agree too.
- Two fields that contradict each other. An individual whose relationship
  names a sex other than the one recorded; a proband recorded as unaffected
  where the basis says they presented with the disease; a variant inherited
  from one parent recorded as homozygous with no second source given; a
  variant recorded de novo in an individual while a parent in the family
  carries it; a parent named as a variant's source whose own link records
  them as not carrying it.
- The same person described two ways. Members of one family whose country
  of origin, ancestry or ethnicity differ when their bases rest on the same
  statement about the family.

What does not count:
- A difference the basis or the cited text explains: the paper tested one
  member another way, gives one member a different diagnosis, or reports a
  value for one person only.
- Values that differ because people differ: sex, affected status and
  proband status vary within a family.
- A value missing where nothing cited says it applies.
- Anything listed in "already_reviewed": a curator has looked at it and
  decided. Do not raise it again in other words.
- Anything an open flag (part 2's list) already raises about the same rows:
  the curator will see it there.

For each inconsistency, return one entry in "inconsistencies" for the row
that is out of line,
not for the rows that agree:
- "about" names that row exactly as the input labels it: "individual /
  variant" (both halves, copied from the input) for a link's value, the
  individual alone for one of their own values, the family for a split
  within a family with no single row out of line.
- The flag's value is a short subject saying what disagrees with what
  ("Missing a testing method the cited cohort statement gives every
  proband").
- Its basis names the values on both sides and the rows that carry them,
  and what the cited text says, so a curator can settle it without
  re-reading the extraction.
- Its citations are the block or blocks the inconsistency turns on, each
  with a quote copied exactly from the block text given. Cite nothing when
  it turns on no block.

When in doubt, leave it out: a missed inconsistency is still in front of the
curator in the tables, while a false one costs them time on every paper.
Return no inconsistencies when the extraction agrees with itself, or when
there is no extraction.

PART 2: REPEATED FLAGS

"Open flags on this paper" is a JSON list of the curator flags the
extraction agents raised. Each has
an id, the agent that raised it, its kind, what it is about (a patient,
family, variant or phenotype, or null), a subject and the basis behind
it. The agents ran separately -- one per patient, per family or per variant,
and at the same time -- so the same decision about the paper may appear more
than once, worded differently or about different people.

Return in "groups" the flags that are ONE decision raised more than once. A
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
nothing repeats. Your own inconsistencies from part 1 are not in the list and
are never grouped.
"""

agent = Agent(
    name='extraction_verifier',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=extraction_model(),
    model_settings=decision_model_settings(),
    output_type=model_facing_output(ExtractionVerificationOutput),
)
