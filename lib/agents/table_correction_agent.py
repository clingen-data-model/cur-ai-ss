"""Agent to correct corrupted table markdown using OpenAI vision."""

import logging
from pathlib import Path

from agents import Agent, function_tool
from pydantic import BaseModel

from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.gcs import upload_and_sign_image
from lib.misc.pdf.paths import (
    pdf_markdown_path,
    pdf_table_image_path,
    pdf_table_vision_markdown_path,
    pdf_tables_dir,
)

setup_logging()
logger = logging.getLogger(__name__)

VISION_EXTRACTION_PROMPT = """
Extract this table as structured markdown.

Use proper markdown table syntax (pipes and dashes).
Preserve all cell content exactly as shown.
Include headers if present.
Return ONLY the markdown table, no other text.
"""


def table_correction_agent_for_image(image_path: Path) -> Agent:
    """Build a table correction agent bound to a specific table image."""

    @function_tool
    def extract_table_from_image() -> str:
        """Extract the current table image as markdown using vision."""
        from openai import OpenAI

        client = OpenAI(api_key=env.OPENAI_API_KEY)
        image_url = upload_and_sign_image(image_path)

        message = client.chat.completions.create(
            model=env.OPENAI_VLM,
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image_url',
                            'image_url': {'url': image_url, 'detail': 'high'},
                        },
                        {
                            'type': 'text',
                            'text': VISION_EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )

        content = message.choices[0].message.content
        return content if content is not None else ''

    return Agent(
        name='table_corrector',
        instructions=TABLE_CORRECTION_INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=TableCorrectionResult,
        tools=[extract_table_from_image],
    )


class TableCorrectionResult(BaseModel):
    """Result of table corruption check and correction."""

    original_markdown: str
    is_corrupted: bool
    corrected_markdown: str | None = None
    conversion_successful: bool = False
    is_recoverable: bool = True


TABLE_CORRECTION_INSTRUCTIONS = """You are an expert at evaluating table markdown quality from PDF extraction.

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
- Content that makes semantic sense

Set conversion_successful to true only if the corrected_markdown is a valid markdown table
with proper pipe delimiters and header rows. If extraction failed or returned invalid
markdown, set it to false.

Some tables cannot be faithfully recovered at all -- for example, dense matrices of tiny
symbols (+/-/*), pedigree/manifestation grids, or images where the cell structure is
genuinely ambiguous. Do not invent or hallucinate content for these. If the table is
corrupted and the image does not yield a faithful, trustworthy markdown table, set
is_recoverable to false and conversion_successful to false. This is an acceptable outcome,
not a failure -- the original markdown will simply be left in place."""


async def correct_tables(paper_id: int, supplement: bool = False) -> None:
    """Correct corrupted table markdown in paper using agent.

    Scans all tables, checks each with agent, generates .vision.md files
    for corrupted ones, and updates raw.md with corrections.
    """
    from agents import Runner

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

        image_path = pdf_table_image_path(paper_id, table_id, supplement=supplement)
        agent = table_correction_agent_for_image(image_path)

        # Build prompt with table markdown only. The vision tool reads the image
        # on demand if the agent decides the markdown is corrupted.
        message = (
            f'Table ID: {table_id}\n\nMarkdown to evaluate:\n```\n{table_markdown}\n```'
        )

        # Run agent
        result = await Runner.run(agent, message)

        if not result.final_output.is_corrupted:
            logger.info(f'Table {table_id} looks OK')
            continue

        if (
            not result.final_output.conversion_successful
            or not result.final_output.corrected_markdown
        ):
            # The table is genuinely unrecoverable (e.g. a dense matrix of
            # symbols with no faithful tabular structure). Leave the original
            # markdown in place rather than failing the whole paper extraction.
            logger.warning(
                f'Table {table_id} is corrupted but could not be recovered; '
                f'leaving original markdown in place (recoverable='
                f'{result.final_output.is_recoverable})'
            )
            continue

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
