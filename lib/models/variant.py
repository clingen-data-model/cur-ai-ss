from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypeAlias

from pydantic import BaseModel, ConfigDict, computed_field, model_validator
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base, PatchModel
from lib.models.datetimes import UtcDatetime
from lib.models.evidence_block import (
    AttributedEvidenceBlock,
    AttributedReasoningBlock,
    EvidenceBlock,
    HumanEvidenceBlock,
    ReasoningBlock,
)
from lib.models.paper import PaperDB
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB
    from lib.models.user import UserDB


def get_variant_description(
    variant_id: int,
    harmonized_variant: 'HarmonizedVariant | HarmonizedVariantDB | HarmonizedVariantResp | None',
    variant_evidence: dict,
) -> str:
    """Generate a human-readable description of a variant, prioritizing harmonized fields."""
    if harmonized_variant:
        hv = harmonized_variant
        return (
            hv.hgvs_c
            or hv.hgvs_g
            or hv.gnomad_style_coordinates
            or hv.rsid
            or hv.hgvs_p
            or variant_evidence.get('value')
            or f'Variant {variant_id}'
        )
    return variant_evidence.get('value') or f'Variant {variant_id}'


# Harmonization succeeded only if it produced at least one identifier the
# downstream lookups can use. hgvs_p is deliberately not in this list: a protein
# change alone cannot be annotated against gnomAD, ClinVar or VEP, which is why
# variant annotation skips these rows.
HARMONIZED_IDENTIFIER_FIELDS = (
    'gnomad_style_coordinates',
    'rsid',
    'caid',
    'hgvs_g',
    'hgvs_c',
)

# Every HGVS c./g. description names the change with one of these. A string
# without any of them is not HGVS -- usually legacy notation that puts the
# reference base before the position ("c.C2665G" for "c.2665C>G"), or a quote
# the PDF mangled ("c.1843-3C 4T", where ">" was read as "4").
_HGVS_CHANGE_OPERATORS = ('>', 'del', 'dup', 'ins', 'inv', 'con', '=')

# Checked for whitespace: no identifier in any of these notations contains a
# space, so one means the value was copied out of a broken table cell.
_UNSPACED_IDENTIFIER_FIELDS = HARMONIZED_IDENTIFIER_FIELDS + ('hgvs_p',)

HarmonizedLike: TypeAlias = (
    'HarmonizedVariant | HarmonizedVariantDB | HarmonizedVariantResp | None'
)


def is_harmonized(harmonized_variant: HarmonizedLike) -> bool:
    """True if harmonization produced at least one usable identifier."""
    if harmonized_variant is None:
        return False
    return any(
        getattr(harmonized_variant, field, None)
        for field in HARMONIZED_IDENTIFIER_FIELDS
    )


def malformed_identifiers(harmonized_variant: HarmonizedLike) -> dict[str, str]:
    """Harmonized identifiers that are not well-formed, keyed by field name.

    Catches what harmonization echoed back rather than normalized. Empty when
    every identifier present looks right, so a truthy result is the warning.
    """
    if harmonized_variant is None:
        return {}

    malformed: dict[str, str] = {}
    for field in _UNSPACED_IDENTIFIER_FIELDS:
        value = getattr(harmonized_variant, field, None)
        if value and any(character.isspace() for character in value):
            malformed[field] = value

    for field in ('hgvs_c', 'hgvs_g'):
        value = getattr(harmonized_variant, field, None)
        if not value or field in malformed:
            continue
        if not any(operator in value for operator in _HGVS_CHANGE_OPERATORS):
            malformed[field] = value

    return malformed


class VariantType(str, Enum):
    missense = 'Missense'
    frameshift = 'Frameshift'
    stop_gained = 'Stop Gained'
    splice_donor = 'Splice Donor'
    splice_acceptor = 'Splice Acceptor'
    splice_region = 'Splice Region'
    start_lost = 'Start Lost'
    inframe_deletion = 'Inframe Deletion'
    frameshift_deletion = 'Frameshift Deletion'
    inframe_insertion = 'Inframe Insertion'
    frameshift_insertion = 'Frameshift Insertion'
    structural = 'Structural'
    synonymous = 'Synonymous'
    intron = 'Intron'
    five_utr = "5' UTR"
    three_utr = "3' UTR"
    non_coding = 'Non-Coding'
    unknown = 'Unknown'


class GenomeBuild(str, Enum):
    GRCh37 = 'GRCh37'
    GRCh38 = 'GRCh38'


class Variant(BaseModel):
    """Variant extracted from paper by the extraction agent."""

    # Variant-level evidence
    variant: EvidenceBlock[Optional[str]]

    # Reference sequences with evidence blocks
    transcript: EvidenceBlock[Optional[str]]
    protein_accession: EvidenceBlock[Optional[str]]
    genomic_accession: EvidenceBlock[Optional[str]]
    lrg_accession: EvidenceBlock[Optional[str]]
    gene_accession: EvidenceBlock[Optional[str]]
    genomic_coordinates: EvidenceBlock[Optional[str]]
    genome_build: EvidenceBlock[Optional[GenomeBuild]]
    rsid: EvidenceBlock[Optional[str]]
    caid: EvidenceBlock[Optional[str]]

    # HGVS with evidence blocks
    hgvs_c: EvidenceBlock[Optional[str]]
    hgvs_p: EvidenceBlock[Optional[str]]
    hgvs_g: EvidenceBlock[Optional[str]]

    # Variant type with evidence
    variant_type: EvidenceBlock[VariantType]

    # Functional evidence assessment with evidence block
    functional_evidence: EvidenceBlock[bool]

    main_focus: EvidenceBlock[bool]


class VariantExtractionOutput(BaseModel):
    """Output from variant extraction agent."""

    variants: List[Variant]


class HarmonizedVariant(BaseModel):
    """Harmonized variant data fields."""

    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    hgvs_g: Optional[str] = None


class HarmonizedVariantResp(BaseModel):
    """Response model for harmonized variants."""

    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    hgvs_g: Optional[str] = None
    updated_by_user_id: int | None = None
    updated_by: UserSummaryResp | None = None


class VariantResp(BaseModel):
    """Response model for extracted variants."""

    id: int
    paper_id: int
    variant: Optional[str]
    transcript: Optional[str]
    protein_accession: Optional[str]
    genomic_accession: Optional[str]
    lrg_accession: Optional[str]
    gene_accession: Optional[str]
    genomic_coordinates: Optional[str]
    genome_build: Optional[str]
    rsid: Optional[str]
    caid: Optional[str]
    hgvs_c: Optional[str]
    hgvs_p: Optional[str]
    hgvs_g: Optional[str]
    variant_type: str
    functional_evidence: bool
    main_focus: bool
    updated_at: UtcDatetime
    updated_by_user_id: int | None = None
    updated_by: UserSummaryResp | None = None
    created_at: UtcDatetime
    created_by_user_id: int | None = None
    created_by: UserSummaryResp | None = None
    # Evidence blocks (from DB JSON columns)
    transcript_evidence: AttributedEvidenceBlock[Optional[str]]
    protein_accession_evidence: AttributedEvidenceBlock[Optional[str]]
    genomic_accession_evidence: AttributedEvidenceBlock[Optional[str]]
    lrg_accession_evidence: AttributedEvidenceBlock[Optional[str]]
    gene_accession_evidence: AttributedEvidenceBlock[Optional[str]]
    genomic_coordinates_evidence: AttributedEvidenceBlock[Optional[str]]
    genome_build_evidence: AttributedEvidenceBlock[Optional[str]]
    rsid_evidence: AttributedEvidenceBlock[Optional[str]]
    caid_evidence: AttributedEvidenceBlock[Optional[str]]
    variant_evidence: AttributedEvidenceBlock[Optional[str]]
    hgvs_c_evidence: AttributedEvidenceBlock[Optional[str]]
    hgvs_p_evidence: AttributedEvidenceBlock[Optional[str]]
    hgvs_g_evidence: AttributedEvidenceBlock[Optional[str]]
    variant_type_evidence: HumanEvidenceBlock[str]
    functional_evidence_evidence: HumanEvidenceBlock[bool]
    main_focus_evidence: HumanEvidenceBlock[bool]
    # Harmonized variant (always present with ReasoningBlock, but value may be None if not yet harmonized)
    harmonized_variant: AttributedReasoningBlock[HarmonizedVariantResp | None]
    # Annotated variant (optional, may not yet be annotated)
    annotated_variant: Optional['AnnotatedVariantResp'] = None

    @computed_field  # type: ignore[misc]
    @property
    def variant_description(self) -> str:
        """Generate a human-readable description of the variant, prioritizing harmonized fields."""
        hv_value = self.harmonized_variant.value if self.harmonized_variant else None
        return get_variant_description(
            self.id,
            hv_value,
            self.variant_evidence.model_dump()
            if hasattr(self.variant_evidence, 'model_dump')
            else {'value': self.variant_evidence.value},
        )


class HarmonizedVariantUpdate(PatchModel):
    """Patch model for updating harmonized variant fields."""

    model_config = ConfigDict(extra='forbid')

    gnomad_style_coordinates: str | None = None
    rsid: str | None = None
    caid: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    hgvs_g: str | None = None

    def apply_to(  # type: ignore[override]
        self,
        obj: 'HarmonizedVariantDB',
        editor: 'UserDB | None' = None,
        session: 'Session | None' = None,
    ) -> None:
        for field, value in self.model_dump(exclude_unset=True).items():
            old_value = getattr(obj, field, None)
            setattr(obj, field, value)
            if editor is not None and session is not None and old_value != value:
                # Local import: edit.py imports Base from lib.models.base, and
                # this module sits below base.py in the same import chain --
                # matches the local-import pattern base.py itself uses for the
                # same reason (see PatchModel._apply_field).
                from lib.models.edit import record_edit

                record_edit(session, obj, field, editor, old_value=old_value)
        self.stamp_updated_by(obj, editor)


class VariantCreateRequest(BaseModel):
    """Request to create a new raw (unharmonized) variant."""

    variant: str | None = None
    transcript: str | None = None
    protein_accession: str | None = None
    genomic_accession: str | None = None
    lrg_accession: str | None = None
    gene_accession: str | None = None
    genomic_coordinates: str | None = None
    genome_build: str | None = None
    rsid: str | None = None
    caid: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    hgvs_g: str | None = None
    variant_type: str = 'Unknown'
    functional_evidence: bool = False
    main_focus: bool = False


class VariantUpdateRequest(PatchModel):
    """Patch model for updating variant fields editable in the UI."""

    model_config = ConfigDict(extra='forbid')

    variant_type: str | None = None
    functional_evidence: bool | None = None
    main_focus: bool | None = None
    harmonized_variant: HarmonizedVariantUpdate | None = None
    variant_type_human_edit_note: str | None = None
    functional_evidence_human_edit_note: str | None = None
    main_focus_human_edit_note: str | None = None

    @model_validator(mode='after')
    def disallow_null_non_nullable_variant_fields(self) -> 'VariantUpdateRequest':
        for field in ('variant_type', 'functional_evidence', 'main_focus'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'{field} cannot be null')
        if (
            'harmonized_variant' in self.model_fields_set
            and self.harmonized_variant is None
        ):
            raise ValueError('harmonized_variant cannot be null')
        return self

    def apply_to(  # type: ignore[override]
        self,
        obj: 'VariantDB',
        editor: 'UserDB | None' = None,
        session: 'Session | None' = None,
    ) -> None:
        for field, value in self.model_dump(exclude_unset=True).items():
            if field == 'harmonized_variant':
                continue
            self._apply_field(obj, field, value, editor, session)
        self.stamp_updated_by(obj, editor)


class VariantDB(Base):
    __tablename__ = 'variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )

    # Core fields
    variant: Mapped[str | None] = mapped_column(String, nullable=True)
    transcript: Mapped[str | None] = mapped_column(String, nullable=True)
    protein_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    genomic_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    lrg_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    gene_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    genomic_coordinates: Mapped[str | None] = mapped_column(String, nullable=True)
    genome_build: Mapped[str | None] = mapped_column(String, nullable=True)
    rsid: Mapped[str | None] = mapped_column(String, nullable=True)
    caid: Mapped[str | None] = mapped_column(String, nullable=True)

    # HGVS
    hgvs_c: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_p: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_g: Mapped[str | None] = mapped_column(String, nullable=True)

    # Variant type
    variant_type: Mapped[str] = mapped_column(String, nullable=False)

    # Functional evidence
    functional_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Main focus
    main_focus: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Evidence blocks (static, immutable)
    transcript_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    protein_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    genomic_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    lrg_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    gene_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    genomic_coordinates_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    genome_build_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    rsid_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    caid_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    variant_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    hgvs_c_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    hgvs_p_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    hgvs_g_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    variant_type_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    functional_evidence_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    main_focus_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # NULL means the extraction pipeline created this row -- see
    # PatientDB.created_by_user_id's comment for why this is a separate
    # column from updated_by_user_id.
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    paper: Mapped[PaperDB] = relationship('PaperDB', back_populates='variants')
    updated_by: Mapped['UserDB | None'] = relationship(
        'UserDB', foreign_keys=[updated_by_user_id]
    )
    created_by: Mapped['UserDB | None'] = relationship(
        'UserDB', foreign_keys=[created_by_user_id]
    )
    harmonized_variant: Mapped['HarmonizedVariantDB | None'] = relationship(
        'HarmonizedVariantDB',
        back_populates='variant',
        uselist=False,
        cascade='all, delete-orphan',
    )
    annotated_variant: Mapped['AnnotatedVariantDB | None'] = relationship(
        'AnnotatedVariantDB',
        back_populates='variant',
        uselist=False,
        cascade='all, delete-orphan',
    )
    patient_variant_occurrences: Mapped[list['PatientVariantOccurrenceDB']] = (
        relationship(
            'PatientVariantOccurrenceDB',
            back_populates='variant',
            cascade='all, delete-orphan',
        )
    )

    __table_args__ = (Index('ix_variants_paper_id', 'paper_id'),)


class HarmonizedVariantDB(Base):
    __tablename__ = 'harmonized_variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('variants.id', ondelete='CASCADE'), nullable=False
    )

    # Harmonized fields
    gnomad_style_coordinates: Mapped[str | None] = mapped_column(String, nullable=True)
    rsid: Mapped[str | None] = mapped_column(String, nullable=True)
    caid: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_c: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_p: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_g: Mapped[str | None] = mapped_column(String, nullable=True)
    reasoning: Mapped[str] = mapped_column(String, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    variant: Mapped['VariantDB'] = relationship(
        'VariantDB', back_populates='harmonized_variant', foreign_keys=[variant_id]
    )
    updated_by: Mapped['UserDB | None'] = relationship('UserDB')

    __table_args__ = (
        UniqueConstraint('variant_id', name='uq_harmonized_variants_variant_id'),
        Index('ix_harmonized_variants_variant_id', 'variant_id'),
    )


class SpliceAI(BaseModel):
    """SpliceAI prediction data from VEP."""

    max_score: float = 0.0
    effect_type: Optional[str] = None
    position: Optional[int] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> 'SpliceAI':
        """Convert raw SpliceAI dict into max_score, effect_type, position."""
        ds_keys = ['DS_AG', 'DS_AL', 'DS_DG', 'DS_DL']
        dp_keys = ['DP_AG', 'DP_AL', 'DP_DG', 'DP_DL']

        max_score = 0.0
        effect_type = None
        position = None

        for ds, dp in zip(ds_keys, dp_keys):
            score = raw.get(ds, 0)
            if score > max_score:
                max_score = score
                effect_type = ds
                position = raw.get(dp)

        return cls(max_score=max_score, effect_type=effect_type, position=position)


class AnnotatedVariant(BaseModel):
    """Annotated variant data from ClinVar, VEP, and gnomAD."""

    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    pathogenicity: Optional[str] = None
    submissions: Optional[int] = None
    stars: Optional[int] = None
    exon: Optional[str] = None
    vep_consequence: Optional[str] = None
    revel: Optional[float] = None
    alphamissense_class: Optional[str] = None
    alphamissense_score: Optional[float] = None
    spliceai: Optional[SpliceAI] = None

    # gnomAD
    gnomad_top_level_af: Optional[float] = None
    gnomad_ac: Optional[int] = None
    gnomad_an: Optional[int] = None
    gnomad_popmax_af: Optional[float] = None
    gnomad_popmax_population: Optional[str] = None
    gnomad_popmax_ac: Optional[int] = None
    gnomad_popmax_an: Optional[int] = None


class VariantAnnotationOutput(BaseModel):
    """Output from variant annotation agent."""

    variants: List[AnnotatedVariant]


class AnnotatedVariantResp(BaseModel):
    """Response model for annotated variants."""

    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    pathogenicity: Optional[str] = None
    submissions: Optional[int] = None
    stars: Optional[int] = None
    exon: Optional[str] = None
    vep_consequence: Optional[str] = None
    revel: Optional[float] = None
    alphamissense_class: Optional[str] = None
    alphamissense_score: Optional[float] = None
    spliceai: Optional[dict] = None  # Serialized SpliceAI

    gnomad_top_level_af: Optional[float] = None
    gnomad_ac: Optional[int] = None
    gnomad_an: Optional[int] = None
    gnomad_popmax_af: Optional[float] = None
    gnomad_popmax_population: Optional[str] = None
    gnomad_popmax_ac: Optional[int] = None
    gnomad_popmax_an: Optional[int] = None


class AnnotatedVariantDB(Base):
    """Annotated variant data persisted to database."""

    __tablename__ = 'annotated_variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('variants.id', ondelete='CASCADE'),
        nullable=False,
    )

    # ClinVar
    pathogenicity: Mapped[str | None] = mapped_column(String, nullable=True)
    submissions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stars: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # VEP
    exon: Mapped[str | None] = mapped_column(String, nullable=True)
    vep_consequence: Mapped[str | None] = mapped_column(String, nullable=True)
    revel: Mapped[float | None] = mapped_column(Float, nullable=True)
    alphamissense_class: Mapped[str | None] = mapped_column(String, nullable=True)
    alphamissense_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    spliceai: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Harmonized variant references
    gnomad_style_coordinates: Mapped[str | None] = mapped_column(String, nullable=True)
    rsid: Mapped[str | None] = mapped_column(String, nullable=True)
    caid: Mapped[str | None] = mapped_column(String, nullable=True)

    # gnomAD
    gnomad_top_level_af: Mapped[float | None] = mapped_column(Float, nullable=True)
    gnomad_ac: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gnomad_an: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gnomad_popmax_af: Mapped[float | None] = mapped_column(Float, nullable=True)
    gnomad_popmax_population: Mapped[str | None] = mapped_column(String, nullable=True)
    gnomad_popmax_ac: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gnomad_popmax_an: Mapped[int | None] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    variant: Mapped['VariantDB'] = relationship(
        'VariantDB',
        back_populates='annotated_variant',
        foreign_keys=[variant_id],
    )

    __table_args__ = (
        UniqueConstraint('variant_id', name='uq_annotated_variants_variant_id'),
        Index('ix_annotated_variants_variant_id', 'variant_id'),
    )
