"""Agent to correct corrupted table markdown using OpenAI vision."""

import asyncio
import base64
import logging
import tempfile
from pathlib import Path

from agents import Agent, function_tool
from pydantic import BaseModel

from lib.core.environment import env
from lib.misc.pdf.paths import (
    pdf_markdown_path,
    pdf_table_image_path,
    pdf_table_markdown_path,
    pdf_table_vision_markdown_path,
    pdf_tables_dir,
)

logger = logging.getLogger(__name__)


def rotate_image_90(image_path: Path) -> Path:
    """Rotate image 90 degrees and save to temporary location."""
    from PIL import Image

    img = Image.open(image_path)
    rotated = img.rotate(90, expand=True)

    rotated_path = Path(tempfile.gettempdir()) / f'{image_path.stem}_rotated.png'
    rotated.save(rotated_path)
    return rotated_path


@function_tool
def extract_table_from_image(image_url: str) -> str:
    """Extract table markdown from image URL using vision."""
    from openai import OpenAI

    client = OpenAI(api_key=env.OPENAI_API_KEY)

    message = client.chat.completions.create(
        model=env.OPENAI_API_DEPLOYMENT,
        messages=[
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': image_url,
                        },
                    },
                    {
                        'type': 'text',
                        'text': """Extract this table as structured markdown.

Use proper markdown table syntax (pipes and dashes).
Preserve all cell content exactly as shown.
Include headers if present.
Return ONLY the markdown table, no other text.""",
                    },
                ],
            }
        ],
    )

    content = message.choices[0].message.content
    return content if content is not None else ''


class TableCorrectionResult(BaseModel):
    """Result of table corruption check and correction."""

    original_markdown: str
    is_corrupted: bool
    corrected_markdown: str | None = None


INSTRUCTIONS = """You are an expert at evaluating table markdown quality from PDF extraction.

Your task:
1. Review the provided table markdown
2. Judge if it's corrupted (headers are gibberish, cells are jumbled, content is nonsensical)
3. If corrupted, use extract_table_from_image to get the corrected version
4. Return the assessment and any corrections

A corrupted table has signs like:
- Headers with excessive parentheses
- Headers with mostly numbers/special chars
- Cell content that's jumbled or doesn't make sense
- Missing actual column headers

A good table has:
- Readable headers describing columns
- Consistent cell alignment
- Content that makes semantic sense"""

agent = Agent(
    name='table_corrector',
    instructions=INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=TableCorrectionResult,
    tools=[extract_table_from_image],
)


async def correct_tables(paper_id: int, supplement: bool = False) -> None:
    """Correct corrupted table markdown in paper using agent.

    Scans all tables, checks each with agent, generates .vision.md files
    for corrupted ones, and updates raw.md with corrections.
    """
    from agents import Runner

    from lib.misc.gcs import upload_and_sign_image

    tables_dir = pdf_tables_dir(paper_id, supplement=supplement)
    if not tables_dir.exists():
        return

    # Find all .md table files
    table_files = sorted(tables_dir.glob('*.md'))
    if not table_files:
        return

    # Track corrections: table_id -> (original_markdown, corrected_markdown)
    corrections: dict[int, tuple[str, str]] = {}

    for table_path in table_files:
        # Skip vision files
        if '.vision' in table_path.name:
            continue

        table_id = int(table_path.stem)
        table_markdown = table_path.read_text()

        logger.info(f'Checking table {table_id} for corruption...')

        # Upload image and get signed URL
        image_path = pdf_table_image_path(paper_id, table_id, supplement=supplement)
        image_url = upload_and_sign_image(image_path)

        # Build prompt with table markdown and image URL
        message = (
            f'Table ID: {table_id}\n\n'
            f'Markdown to evaluate:\n```\n{table_markdown}\n```\n\n'
            f'Image URL for extraction if needed: {image_url}'
        )

        # Run agent
        result = await Runner.run(agent, message)

        if not result.final_output.is_corrupted:
            logger.info(f'Table {table_id} looks OK')
            continue

        if not result.final_output.corrected_markdown:
            logger.info(
                f'Table {table_id} extraction failed on first attempt, retrying with rotated image...'
            )
            rotated_image_path = rotate_image_90(image_path)
            rotated_image_url = upload_and_sign_image(rotated_image_path)

            message = (
                f'Table ID: {table_id}\n\n'
                f'Markdown to evaluate:\n```\n{table_markdown}\n```\n\n'
                f'Image URL for extraction if needed: {rotated_image_url}'
            )

            result = await Runner.run(agent, message)

            if not result.final_output.corrected_markdown:
                raise ValueError(
                    f'Table {table_id} was detected as corrupted but no corrected markdown was generated even after rotation retry'
                )

        logger.info(f'Table {table_id} was corrupted, corrected version ready')

        # Write vision file
        vision_path = pdf_table_vision_markdown_path(
            paper_id, table_id, supplement=supplement
        )
        vision_path.write_text(result.final_output.corrected_markdown)
        logger.info(f'Wrote {vision_path}')

        corrections[table_id] = (
            result.final_output.original_markdown,
            result.final_output.corrected_markdown,
        )

    if not corrections:
        return

    # Replace corrupted tables in raw.md
    raw_md_path = pdf_markdown_path(paper_id, supplement=supplement)
    raw_md = raw_md_path.read_text()

    # For each correction, find exact byte-for-byte match and replace
    for table_id, (original_md, corrected_md) in corrections.items():
        if original_md in raw_md:
            raw_md = raw_md.replace(original_md, corrected_md, 1)
            logger.info(f'Replaced table {table_id} in raw.md')
        else:
            logger.warning(f'Could not find table {table_id} byte-for-byte in raw.md')

    # Write updated markdown
    raw_md_path.write_text(raw_md)
    logger.info(f'Updated {raw_md_path} with corrected tables')
