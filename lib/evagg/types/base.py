import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from lib.evagg.utils.environment import env


@dataclass(eq=False)
class Paper:
    id: str
    content: bytes | None = None

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
