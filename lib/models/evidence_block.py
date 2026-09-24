import re
from datetime import datetime
from typing import ClassVar, Generic, Self, TypeVar

from pydantic import BaseModel, field_validator, model_validator

from lib.models.datetimes import UtcDatetime

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


class EvidenceBlock(ReasoningBlock[T]):
    quote: str | None = None  # verbatim quote from text
    table_id: int | None = None  # table-based evidence
    image_id: int | None = None  # figure/pedigree evidence
    is_supplement: bool = (
        False  # whether evidence came from a supplement (non-renderable in PDF view)
    )

    # Whether a non-empty value must cite a quote/table/image. True for what an
    # agent produces; the response-side subclasses below turn it off, since a
    # curator-typed value legitimately has no source to cite.
    require_source: ClassVar[bool] = True

    @field_validator('quote', mode='after')
    @classmethod
    def _strip_quote_markup(cls, value: str | None) -> str | None:
        return strip_markup(value) if value else value

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
            and not self.quote
            and self.table_id is None
            and self.image_id is None
        ):
            raise ValueError(
                'At least one evidence source must be provided: '
                'quote, table_id, or image_id'
            )

        # Prioritize table_id if both are provided
        if self.table_id is not None and self.image_id is not None:
            self.image_id = None

        return self


# ReasoningBlock/EvidenceBlock above are agent output schemas and the shape
# stored in the DB's evidence JSON, so they carry no "who edited this" fields:
# anything on them is sent to the model to fill in (and counts toward
# Anthropic's 16 union/nullable-node schema limit), and anything stored would
# be a frozen copy of what the edits table already records. The Attributed*
# classes below are the API-response shapes; their edited_* fields are filled
# in from the edits table while the response is built (see app.py's
# _attach_edit_history), never read from storage.


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
