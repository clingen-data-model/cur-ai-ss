import logging
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, ClassVar, Generic, Self, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from lib.misc.pdf.anchor_ids import parse_anchor
from lib.models.datetimes import UtcDatetime

logger = logging.getLogger(__name__)

T = TypeVar('T')

# A table rebuilt from its image comes back as rich markdown: footnote markers
# as <sup>g</sup>, in-cell line breaks as <br>, because plain markdown cannot
# express either. Quotes are copied from that text verbatim, so the tags rode
# into the evidence and out to curators, who see them literally -- Streamlit
# escapes HTML rather than rendering it.
#
# They are stripped here, on the way in, so every path that builds a block gets
# it and nothing downstream has to remember. Highlighting is unaffected: quotes
# are matched against words extracted from the PDF page, which never had tags in
# it, so their absence brings the two closer together rather than further apart.
_BR = re.compile(r'<br\s*/?>', re.IGNORECASE)
# One or two letters in a superscript is a footnote marker and goes with the
# tag. Leaving the letter behind turns "Fs 3" into "Fs 3g", which reads as part
# of the value and is exactly how a mangled table looks.
_FOOTNOTE = re.compile(r'<(sup|sub)>([A-Za-z]{1,2})</\1>', re.IGNORECASE)
# Anything else is data -- an exponent, an allele label -- written the way plain
# text has always written it, 10^6 rather than the 106 that stripping alone
# would leave.
_SUP = re.compile(r'<sup>([^<]+)</sup>', re.IGNORECASE)
_SUB = re.compile(r'<sub>([^<]+)</sub>', re.IGNORECASE)
# Only real tag names, never a catch-all. "<[^>]+>" looks equivalent and is
# not: these papers use "<" as data ("<2" of normal activity) and ">" as data
# (c.361G>C), so a greedy pattern matches from one to the other and eats what
# lies between -- "LDL activity <2 and c.361G>C" came out as "LDL activity C".
_TAG = re.compile(
    r'</?(?:br|sup|sub|b|i|em|strong|u|s|span|small|code|a|p|div|'
    r'table|thead|tbody|tr|td|th|ul|ol|li)(?:\s[^<>]*)?/?>',
    re.IGNORECASE,
)


def strip_markup(text: str) -> str:
    """Remove inline HTML from text meant to be read by a curator.

    A bare "<" is left alone: "<2" is a real value in these papers, not markup.

    Text carrying no markup is returned untouched, not merely unchanged: a quote
    is verbatim so it can be matched back against words extracted from the page,
    and reflowing its whitespace on the way past would be a modification nobody
    asked for.
    """
    if '<' not in text:
        return text
    text = _BR.sub(' ', text)
    text = _FOOTNOTE.sub('', text)
    text = _SUP.sub(r'^\1', text)
    text = _SUB.sub(r'_\1', text)
    text = _TAG.sub('', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


class ReasoningBlock(BaseModel, Generic[T]):
    value: T
    reasoning: str  # human-readable summary (always required)

    @field_validator('reasoning', mode='after')
    @classmethod
    def _strip_markup(cls, value: str) -> str:
        return strip_markup(value)


# One structural reference into an anchored document (``anchored.md``).
#
# The anchor names a block the agent was shown as a ``[paragraph-54]`` /
# ``[table-1]`` / ``[figure-2]`` tag, or a table row copied from the ``anchor``
# column (``table-1-row-7``). The quote narrows the highlight inside that
# block; it is never the whole block, because the anchor already names it. A
# table cell is cited as its row plus the cell's text as the quote (no column
# grammar: the agent copies, it never counts columns).
#
# Every field is a plain ``str`` on purpose: Anthropic counts nullable and
# union nodes in the output schema against a hard limit, per use of the block
# that embeds this, so a ``str | None`` here would be paid for hundreds of
# times over (see the schema-limit note below ``EvidenceBlock``).
#
# A comment rather than a docstring: Pydantic copies a class docstring into
# the JSON schema as its description, and the manual-output agents embed that
# schema in their prompt, so a docstring here is text the model reads.
class Citation(BaseModel):
    """One place in the paper that supports a value: a block id and a span of it."""

    anchor: str = Field(
        description=(
            'A block id exactly as printed in the text, e.g. paragraph-54, '
            'table-1, table-1-row-7, figure-2, or supp-table-1-row-7 for the '
            'supplement.'
        )
    )
    quote: str = Field(
        default='',
        description=(
            'The shortest verbatim span of that block that supports the value: '
            'a phrase or sentence of a paragraph, or the text of one table cell. '
            'Empty when the whole block is the evidence (always empty for a '
            'figure).'
        ),
    )

    @field_validator('anchor', mode='after')
    @classmethod
    def _strip_anchor(cls, value: str) -> str:
        return value.strip()

    @field_validator('quote', mode='after')
    @classmethod
    def _strip_quote_markup(cls, value: str) -> str:
        return strip_markup(value) if value else value


class EvidenceBlock(ReasoningBlock[T]):
    # Structural evidence: ids of blocks in the anchored document
    # (docs/evidence-anchors-plan.md). Rows written before slice 4 may still
    # carry the retired quote/table_id/image_id/is_supplement keys in their
    # stored JSON; Pydantic ignores them on load, and they are not served.
    citations: list[Citation] = Field(
        default=[],
        description=(
            'Structural anchors for this evidence. Only cite ids that appear as '
            '[anchor-id] tags in the text you were given; if the text carries no '
            'such tags, leave this empty.'
        ),
    )

    # Whether a non-empty value must cite at least one anchor. True for what an
    # agent produces; the response-side subclasses below turn it off, since a
    # curator-typed value legitimately has no source to cite.
    require_source: ClassVar[bool] = True

    @field_validator('citations', mode='after')
    @classmethod
    def _drop_malformed_citations(cls, citations: list[Citation]) -> list[Citation]:
        """Keep only citations whose anchor is a well-formed id.

        Lenient about form, strict about presence: a mangled id is dropped with
        a warning rather than failing the whole agent output, and if it was the
        block's only source ``validate_sources`` (which runs after the field
        validators) raises exactly as it would for a block with no source.
        Cannot live on ``Citation``: a validator cannot remove its own item.
        Whether the id actually exists in the paper is ``verify_citations``' job.
        """
        kept = []
        for citation in citations:
            if parse_anchor(citation.anchor) is None:
                logger.warning(
                    'Dropping citation with malformed anchor %r', citation.anchor
                )
                continue
            kept.append(citation)
        return kept

    @model_validator(mode='after')
    def validate_sources(self) -> Self:
        if not self.reasoning.strip():
            raise ValueError('reasoning must be non-empty')

        # Skip evidence source requirement if value is None or UNKNOWN
        is_unknown = (
            self.value is None
            or self.value == 'Unknown'
            or (hasattr(self.value, 'value') and self.value.value == 'Unknown')
        )

        # For boolean values, skip validation if value is falsy (no evidence required for False)
        is_falsy_bool = isinstance(self.value, bool) and not self.value

        if (
            self.require_source
            and not is_unknown
            and not is_falsy_bool
            and not self.citations
        ):
            raise ValueError('At least one citation is required')

        return self


def _norm(text: str) -> str:
    """Markup- and whitespace-tolerant form for comparing a quote to its block."""
    return ' '.join(strip_markup(text).split())


class CitationError(ValueError):
    """An agent cited something the paper does not contain.

    Raised by ``verify_citations`` with one line per bad citation, worded for
    the model: the repair loop sends the message straight back, so it names
    the field, the anchor and what was wrong.
    """


def _citation_problems(model: Any, texts: Mapping[str, str], path: str) -> list[str]:
    if isinstance(model, EvidenceBlock):
        problems = []
        for i, citation in enumerate(model.citations):
            where = f'{path}.citations[{i}]' if path else f'citations[{i}]'
            block = texts.get(citation.anchor)
            if block is None:
                problems.append(
                    f'{where}: anchor {citation.anchor!r} does not exist in the '
                    'paper; copy an id exactly as printed in the text'
                )
            elif citation.quote and _norm(citation.quote) not in _norm(block):
                problems.append(
                    f'{where}: quote {citation.quote!r} is not found verbatim in '
                    f'{citation.anchor}; copy a span of that block or leave the '
                    'quote empty'
                )
        return problems
    if isinstance(model, BaseModel):
        return [
            problem
            for name in type(model).model_fields
            for problem in _citation_problems(
                getattr(model, name), texts, f'{path}.{name}' if path else name
            )
        ]
    if isinstance(model, list):
        return [
            problem
            for i, item in enumerate(model)
            for problem in _citation_problems(item, texts, f'{path}[{i}]')
        ]
    if isinstance(model, dict):
        return [
            problem
            for key, item in model.items()
            for problem in _citation_problems(item, texts, f'{path}[{key!r}]')
        ]
    return []


def verify_citations(model: Any, texts: Mapping[str, str]) -> None:
    """Raise ``CitationError`` unless every citation names a real block and
    every quote is found inside its block.

    The check behind the grammar validator above: an agent can produce a
    well-formed id that names nothing (``paragraph-999``) or a quote it did not
    actually copy. ``texts`` is id -> block text, as ``paper_block_texts``
    builds it from ``anchored.md`` (main and supplement merged); by
    construction its keys are exactly the ids that exist. Walks any Pydantic
    model, list or dict and reports every problem at once, with the path to
    the field, so a handler can hand the message to the model as a repair
    prompt (``run_with_checked_output``). Nothing is dropped or blanked: a
    value whose evidence does not check out is not stored.

    Quote matching is verbatim after stripping markup and collapsing
    whitespace, no case folding.
    """
    problems = _citation_problems(model, texts, '')
    if problems:
        raise CitationError(
            f'{len(problems)} citation(s) do not check out against the paper:\n'
            + '\n'.join(f'- {problem}' for problem in problems)
        )


# ReasoningBlock/EvidenceBlock above are agent output schemas and the shape
# stored in the DB's evidence JSON, so they carry no "who edited this" fields:
# anything on them is sent to the model to fill in (and counts toward
# Anthropic's 16 union/nullable-node schema limit), and anything stored would
# be a frozen copy of what the edits table already records. The Attributed*
# classes below are the API-response shapes; their edited_* fields are filled
# in from the edits table while the response is built (see app.py's
# _attach_edit_history), never read from storage.
#
# The same limit is why Citation is all-str and citations is a plain list: a
# list is not a union node and neither is a required str, so the field adds
# nothing to the count however many times a block is embedded. A block
# contributes only its value's own nullability (test_output_schema_census
# pins the per-agent totals).


class AttributedReasoningBlock(ReasoningBlock[T]):
    edited_by_user_id: int | None = None
    edited_by_name: str | None = None
    edited_by_is_active: bool | None = None
    edited_at: UtcDatetime | None = None


class AttributedEvidenceBlock(EvidenceBlock[T]):
    require_source: ClassVar[bool] = False

    edited_by_user_id: int | None = None
    edited_by_name: str | None = None
    edited_by_is_active: bool | None = None
    edited_at: UtcDatetime | None = None


class HumanEvidenceBlock(AttributedEvidenceBlock[T]):
    human_edit_note: str | None = None  # optional annotation by human curator
    # The value this field held immediately before the edit in edited_*, resolved
    # the same way (live, from the edits table) -- None both when there is no
    # edit and when the edit's old_value genuinely was empty/never set.
    previous_value: T | None = None


ATTRIBUTION_FIELDS = frozenset(
    {'edited_by_user_id', 'edited_by_name', 'edited_by_is_active', 'edited_at'}
)
