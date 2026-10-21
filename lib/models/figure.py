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
    description: str
    image_url: str
