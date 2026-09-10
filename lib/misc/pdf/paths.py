import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from lib.core.environment import env

if TYPE_CHECKING:
    from lib.models.paper import FileFormat

SUPPLEMENTARY_MATERIAL_HEADER = '# Supplementary Material'


def pdf_dir(paper_id: int) -> Path:
    return env.extracted_pdf_dir / str(paper_id)


def pdf_supplements_dir(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'supplements'


def snapshots_dir(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'snapshots'


def pdf_raw_path(
    paper_id: int, supplement: bool = False, file_format: str | None = None
) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    if supplement and file_format:
        return base / f'raw.{file_format}'
    return base / 'raw.pdf'


def pdf_thumbnail_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'thumbnail.png'


def pdf_tables_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'tables'


def pdf_images_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'images'


def pdf_sections_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'sections'


def pdf_markdown_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'raw.md'


def pdf_json_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'raw.json'


def pdf_words_json_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'words.json'


def pdf_highlighted_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'highlighted.pdf'


def pdf_extraction_success_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / '_SUCCESS'


def pdf_image_path(paper_id: int, image_id: int, supplement: bool = False) -> Path:
    return pdf_images_dir(paper_id, supplement) / f'{image_id}.png'


def pdf_image_caption_path(
    paper_id: int, image_id: int, supplement: bool = False
) -> Path:
    return pdf_images_dir(paper_id, supplement) / f'{image_id}.md'


def pdf_table_image_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.png'


def pdf_table_markdown_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.md'


def pdf_table_vision_markdown_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.vision.md'


def pdf_table_correction_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    """Record of what the correction agent decided about one table."""
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.correction.json'


def pdf_section_markdown_path(
    paper_id: int, section_id: int, supplement: bool = False
) -> Path:
    return pdf_sections_dir(paper_id, supplement) / f'{section_id}.md'


def paper_section_classification_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'paper_section_classification.json'


def apply_table_corrections(
    paper_id: int, markdown: str, supplement: bool = False
) -> str:
    """Replace corrupted table markdown with its vision-corrected version.

    ``correct_tables`` writes a ``<table_id>.vision.md`` beside every table it
    re-extracted from the table image, and leaves ``raw.md`` untouched. The
    substitution happens here, at read time, keyed on the on-disk table
    markdown -- which is byte-identical to the copy docling inlined into
    ``raw.md`` -- so the match is exact by construction. Tables with no vision
    file are left as they are.
    """
    tables_dir = pdf_tables_dir(paper_id, supplement=supplement)
    if not tables_dir.exists():
        return markdown

    for vision_path in sorted(tables_dir.glob('*.vision.md')):
        table_id = vision_path.name.removesuffix('.vision.md')
        original_path = tables_dir / f'{table_id}.md'
        if not original_path.exists():
            continue
        original = original_path.read_text()
        if original and original in markdown:
            markdown = markdown.replace(original, vision_path.read_text(), 1)

    return _flag_unrecovered_tables(paper_id, markdown, supplement=supplement)


# Deliberately asks for nothing the reader cannot do: the extraction agents have
# no tools, so telling them to check the table image would invite claiming an
# image they never saw -- the same confabulation this marker exists to prevent.
UNRECOVERED_TABLE_MARKER = (
    '**[EXTRACTION WARNING - TABLE {table_id}: this table could not be read '
    'reliably. The rows below are scrambled: cells may be missing, misaligned, '
    'or under the wrong header. Treat values here as unreliable and prefer any '
    'other source in the paper. Do NOT conclude that a value is absent from the '
    'paper because it is absent from this table -- report it as unreadable '
    'instead.]**'
)


def _flag_unrecovered_tables(
    paper_id: int, markdown: str, supplement: bool = False
) -> str:
    """Mark tables the correction agent judged corrupted but could not recover.

    Without this the scrambled table is indistinguishable from a table that
    genuinely lacks the value, and extraction agents report a confident
    "not stated in the paper" for data that is present but unreadable.
    """
    tables_dir = pdf_tables_dir(paper_id, supplement=supplement)

    for record_path in sorted(tables_dir.glob('*.correction.json')):
        table_id = record_path.name.removesuffix('.correction.json')
        try:
            record = json.loads(record_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        if not record.get('is_corrupted') or record.get('corrected'):
            continue

        original_path = tables_dir / f'{table_id}.md'
        if not original_path.exists():
            continue
        original = original_path.read_text()
        if original and original in markdown:
            marker = UNRECOVERED_TABLE_MARKER.format(table_id=table_id)
            markdown = markdown.replace(original, f'{marker}\n\n{original}', 1)

    return markdown


def raw_md(paper_id: int, supplement: bool = False) -> str:
    """Read a paper's extracted markdown with table corrections applied."""
    path = pdf_markdown_path(paper_id, supplement=supplement)
    return apply_table_corrections(paper_id, path.read_text(), supplement=supplement)


def fulltext_md(paper_id: int, supplement_format: 'FileFormat | None' = None) -> str:
    main_md = raw_md(paper_id)
    supplement_md = pdf_markdown_path(paper_id, supplement=True)
    if supplement_md.exists():
        supplement_header = SUPPLEMENTARY_MATERIAL_HEADER
        if supplement_format:
            supplement_header += f' ({supplement_format.value.upper()})'
        return (
            main_md
            + '\n\n---\n\n'
            + supplement_header
            + '\n\n'
            + raw_md(paper_id, supplement=True)
        )
    return main_md


def relevant_sections_md(
    paper_id: int,
    supplement_format: 'FileFormat | None' = None,
    section_classifications: dict | None = None,
) -> str:
    """Return paper markdown with irrelevant sections removed.

    Falls back to fulltext_md if section classification has not been run yet.
    Splices directly from raw.md: when a classified irrelevant section header is
    encountered, lines are skipped until the next heading that is not.

    A heading the classifier never named ends the skip rather than continuing it.
    The classifier's job is to name the sections worth dropping, so a heading it
    did not name is not one it judged irrelevant, and inheriting the previous
    verdict would be this function deciding that on its behalf.

    Args:
        paper_id: ID of the paper
        supplement_format: Format of supplement if present
        section_classifications: Classification data (from paper.section_classifications).
                                If not provided, returns fulltext.
    """
    # If no classifications provided, return fulltext
    if section_classifications is None:
        return fulltext_md(paper_id, supplement_format)

    classified: dict[str, bool] = {
        s['header'].lower(): s.get('relevant', True)
        for s in section_classifications.get('sections', [])
    }

    main_md = raw_md(paper_id)
    lines = main_md.splitlines(keepends=True)
    result_lines: list[str] = []
    skip = False
    for line in lines:
        heading_match = re.match(r'^#{1,3} (.+)', line.rstrip())
        if heading_match:
            header_text = heading_match.group(1).strip().lower()
            if header_text in classified:
                skip = not classified[header_text]
            else:
                # Headings go unmatched routinely: the classifier is asked for
                # the headers it finds and writes them back in its own words,
                # expanding "Table 1" to the caption underneath it or adding a
                # note like "(table)", so the string no longer matches the line
                # it came from. Carrying the previous verdict through those made
                # one irrelevant section swallow the rest of the file -- papers
                # that print their tables after the references lost every one of
                # them, with nothing to show it had happened.
                skip = False
        if not skip:
            result_lines.append(line)

    filtered_md = ''.join(result_lines)

    supplement_md = pdf_markdown_path(paper_id, supplement=True)
    if supplement_md.exists():
        supplement_header = SUPPLEMENTARY_MATERIAL_HEADER
        if supplement_format:
            supplement_header += f' ({supplement_format.value.upper()})'
        return (
            filtered_md
            + '\n\n---\n\n'
            + supplement_header
            + '\n\n'
            + raw_md(paper_id, supplement=True)
        )

    return filtered_md


def sections_md(paper_id: int) -> list[str]:
    sections = []
    for section_path in pdf_sections_dir(paper_id).iterdir():
        if section_path.suffix == '.md':
            with section_path.open('r') as f:
                sections.append(f.read())
    return sections


def tables_md(paper_id: int) -> list[str]:
    tables = []
    for table_path in pdf_tables_dir(paper_id).iterdir():
        if table_path.suffix == '.md':
            with table_path.open('r') as f:
                tables.append(f.read())
    return tables
