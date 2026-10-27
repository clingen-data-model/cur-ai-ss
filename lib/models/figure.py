"""A figure the Figure Description step read for curation evidence.

One row per described figure of a paper. ``kinds`` says what the figure
shows, from the closed list extraction reads (``FigureKind``); a figure may
hold more than one (a pedigree beside its Sanger traces). The description is
the vision model's analysis, which the downstream agents read as text and
cite by the figure's anchor.
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base

if TYPE_CHECKING:
    from lib.models.paper import PaperDB


class FigureKind(StrEnum):
    """What a described figure shows, in curator words.

    The readable value is what the JSON column and the API carry, so a row
    reads as ``["Pedigree", "Chromatogram"]`` on disk and in a snapshot.
    """

    PEDIGREE = 'Pedigree'
    CHROMATOGRAM = 'Chromatogram'
    GEL = 'Gel'
    COPY_NUMBER_PLOT = 'Copy-number plot'
    READ_PILEUP = 'Read pileup'
    KARYOTYPE_OR_FISH = 'Karyotype or FISH'


class CaptionSource(StrEnum):
    """Where a stored caption came from, so a reader knows how far to trust it.

    DOCLING and ADJACENT are the paper's own words, copied: the first linked
    to the picture by the PDF parser, the second the heading or paragraph
    printed beside an unlinked picture, taken by rule (see the rule above
    ``_legend_item`` in lib/misc/pdf/anchors.py). MODEL_CHOSEN is
    also a copied block, but the vision model picked which, from the prose
    around the figure, having looked at the picture. MODEL_TRANSCRIBED is
    the model's reading of a legend printed inside the image, the one kind
    of caption no block of the text holds (``find_legend``).
    """

    DOCLING = 'Docling'
    ADJACENT = 'Adjacent text'
    MODEL_CHOSEN = 'Model chose'
    MODEL_TRANSCRIBED = 'Model transcribed'


class FigureDescriptionDB(Base):
    __tablename__ = 'figure_descriptions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('papers.id', ondelete='CASCADE'),
        nullable=False,
    )
    # The Docling picture index: the N of the figure-N anchor the other agents
    # cite and of documents/{id}/{main,supplement}/images/N.png.
    image_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # image_id is namespaced separately per supplement/main (see
    # document_image_path), so this is required to know which file it names.
    is_supplement: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default='0'
    )
    # FigureKind values, as strings.
    kinds: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    # The legend as printed, as the anchored document carries it (the alt text
    # of the figure's line) and as the step read it to the vision model. None
    # when Docling attached no caption to the picture. Rows from before
    # b7e2f9c4d6a1 are filled by lib.bin.backfill_figure_captions.
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How the caption was arrived at; None whenever caption is. Stored by
    # member name (SQLEnum default), nullable with no default.
    caption_source: Mapped[CaptionSource | None] = mapped_column(
        SQLEnum(CaptionSource), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped['PaperDB'] = relationship(
        'PaperDB', back_populates='figure_descriptions'
    )

    __table_args__ = (
        UniqueConstraint('paper_id', 'is_supplement', 'image_id'),
        Index('ix_figure_descriptions_paper_id', 'paper_id'),
    )

    def shows(self, kind: FigureKind) -> bool:
        return kind.value in self.kinds


def described_figures(session: Session, paper_id: int) -> list[FigureDescriptionDB]:
    """The paper's described figures, main text first, in figure order."""
    return (
        session.query(FigureDescriptionDB)
        .filter(FigureDescriptionDB.paper_id == paper_id)
        .order_by(FigureDescriptionDB.is_supplement, FigureDescriptionDB.image_id)
        .all()
    )


def pedigree_figure(session: Session, paper_id: int) -> FigureDescriptionDB | None:
    """The first described pedigree: what the downstream agents read until
    they are handed every described figure."""
    return next(
        (
            f
            for f in described_figures(session, paper_id)
            if f.shows(FigureKind.PEDIGREE)
        ),
        None,
    )


class FigureDescriptionResp(BaseModel):
    image_id: int
    is_supplement: bool
    # The id printed in the anchored text (figure-N or supp-figure-N).
    anchor: str
    kinds: list[FigureKind]
    # The legend, and how it was arrived at (see CaptionSource); both None
    # when the figure has none.
    caption: str | None
    caption_source: CaptionSource | None
    description: str
    image_url: str
