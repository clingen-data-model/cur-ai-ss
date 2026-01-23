import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from lib.evagg.utils.environment import env


@dataclass(eq=False)
class Paper:
    id: str
    content: bytes | None = None

    # core bibliographic fields
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None

    title: str | None = None
    abstract: str | None = None
    journal: str | None = None
    first_author: str | None = None
    pub_year: int | None = None
    citation: str | None = None

    # access / licensing
    OA: bool | None = None
    can_access: bool | None = None
    license: str | None = None
    link: str | None = None

    @classmethod
    def from_content(cls, content: bytes) -> 'Paper':
        h = hashlib.sha256()
        h.update(content)
        return Paper(
            id=h.hexdigest(),
            content=content,
        )

    def with_content(self) -> 'Paper':
        if not self.pdf_raw_path.exists():
            raise RuntimeError('Raw PDF must exist prior to calling this method')
        with open(self.pdf_raw_path, 'rb') as f:
            self.content = f.read()
        return self

    def with_metadata(self) -> 'Paper':
        kwargs = {}
        if self.metadata_json_path.exists():
            with open(self.metadata_json_path, 'r') as f:
                kwargs = json.load(f)
        return self.with_kwargs(**kwargs)

    def with_kwargs(self, **kwargs: Any) -> 'Paper':
        """
        Split known fields from unknown ones.
        """
        field_names = {f.name for f in self.__dataclass_fields__.values()}
        known = {k: v for k, v in kwargs.items() if k in field_names}
        return Paper(
            **{
                **self.__dict__,
                **known,
            }
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Paper) and self.id == other.id

    def __repr__(self) -> str:
        text = self.title or self.citation or self.abstract or 'unknown'
        snippet = str(text)[:15] + ('...' if len(text) > 15 else '')
        return f'id: {self.id} - "{snippet}"'

    @property
    def fulltext_md(self) -> str:
        with open(self.pdf_markdown_path, 'r') as f:
            return f.read()

    @property
    def sections_md(self) -> list[str]:
        sections = []
        for section_path in self.pdf_sections_dir.iterdir():
            if str(section_path).endswith('md'):
                with open(section_path, 'r') as f:
                    sections.append(f.read())
        return sections

    @property
    def tables_md(self) -> list[str]:
        tables = []
        for table_path in self.pdf_tables_dir.iterdir():
            if str(table_path).endswith('md'):
                with open(table_path, 'r') as f:
                    tables.append(f.read())
        return tables

    @property
    def evagg_observations_path(self) -> Path:
        return env.evagg_dir / self.id / 'observations.json'

    @property
    def metadata_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'metadata.json'

    @property
    def pdf_dir(self) -> Path:
        return env.extracted_pdf_dir / self.id

    @property
    def pdf_raw_path(self) -> Path:
        return self.pdf_dir / 'raw.pdf'

    @property
    def pdf_thumbnail_path(self) -> Path:
        return self.pdf_dir / 'thumbnail.png'

    @property
    def pdf_tables_dir(self) -> Path:
        return self.pdf_dir / 'tables'

    @property
    def pdf_images_dir(self) -> Path:
        return self.pdf_dir / 'images'

    @property
    def pdf_sections_dir(self) -> Path:
        return self.pdf_dir / 'sections'

    @property
    def pdf_markdown_path(self) -> Path:
        return self.pdf_dir / 'raw.md'

    @property
    def pdf_json_path(self) -> Path:
        return self.pdf_dir / 'raw.json'

    @property
    def pdf_words_json_path(self) -> Path:
        return self.pdf_dir / 'words.json'

    @property
    def pdf_extraction_success_path(self) -> Path:
        return self.pdf_dir / '_SUCCESS'

    def pdf_image_path(
        self,
        image_id: int,
    ) -> Path:
        return self.pdf_images_dir / f'{image_id}.png'

    def pdf_image_caption_path(
        self,
        image_id: int,
    ) -> Path:
        return self.pdf_images_dir / f'{image_id}.md'

    def pdf_table_image_path(
        self,
        table_id: int,
    ) -> Path:
        return self.pdf_tables_dir / f'{table_id}.png'

    def pdf_table_markdown_path(
        self,
        table_id: int,
    ) -> Path:
        return self.pdf_tables_dir / f'{table_id}.md'

    def pdf_section_markdown_path(
        self,
        section_id: int,
    ) -> Path:
        return self.pdf_sections_dir / f'{section_id}.md'


@dataclass(frozen=True)
class HGVSVariant:
    """A representation of a genetic variant."""

    hgvs_desc: str
    gene_symbol: str | None
    refseq: str | None
    refseq_predicted: bool
    valid: bool
    validation_error: str | None
    # TODO, consider subclasses for different variant types.
    protein_consequence: 'HGVSVariant | None'
    coding_equivalents: 'List[HGVSVariant]'

    def __str__(self) -> str:
        """Obtain a string representation of the variant."""
        return f'{self.refseq}:{self.hgvs_desc}'

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HGVSVariant):
            return False
        return (
            self.refseq == other.refseq
            and self.gene_symbol == other.gene_symbol
            and self._comparable() == other._comparable()
        )

    def __hash__(self) -> int:
        return hash((self.refseq, self.gene_symbol, self._comparable()))

    def _comparable(self) -> str:
        """Return a string representation of the variant description that is suitable for direct string comparison.

        This includes
        - dropping of prediction parentheses.
        - substitution of * for Ter in the three letter amino acid representation.

        For example: p.(Arg123Ter) -> p.Arg123*
        """
        # TODO, consider normalization via mutalyzer
        return self.hgvs_desc.replace('(', '').replace(')', '').replace('Ter', '*')

    def get_unique_id(self, prefix: str, suffix: str) -> str:
        # Build a unique id and make it URL-safe.
        id = f'{prefix}_{self.hgvs_desc}_{suffix}'.replace(' ', '')
        return id.replace(':', '-').replace('/', '-').replace('>', '-')
