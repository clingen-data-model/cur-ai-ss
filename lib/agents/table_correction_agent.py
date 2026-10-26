"""Agent to correct corrupted table markdown using the vision model."""

import json
import logging
import re
from pathlib import Path

from agents import Agent, Runner, function_tool
from agents.exceptions import MaxTurnsExceeded
from pydantic import BaseModel

from lib.agents.model_facing import model_facing_output
from lib.agents.model_factory import ModelDeclined, model_settings_for, resolve_model
from lib.agents.vision import vlm_describe
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.images import image_to_data_url
from lib.misc.pdf.paths import (
    document_table_image_path,
    document_table_unrecovered_path,
    document_table_vision_markdown_path,
    document_tables_dir,
)

setup_logging()
logger = logging.getLogger(__name__)

# A judge run is two model turns: one that calls extract_table_from_image (or
# answers outright for a clean table), one that returns the verdict. Twice
# that is room for a retry of a malformed answer; it is not room for the
# SDK's default of ten, which on a classifier refusal is ten billed copies of
# the same empty turn before MaxTurnsExceeded (see ModelDeclined).
JUDGE_MAX_TURNS = 4

VISION_EXTRACTION_PROMPT = """
Extract this table as structured markdown.

Use proper markdown table syntax (pipes and dashes).
Preserve all cell content exactly as shown.
Include headers if present.
Return ONLY the markdown table, no other text.
"""


def table_correction_agent_for_image(image_path: Path) -> Agent:
    """Build a table correction agent bound to a specific table image."""

    # failure_error_function=None so a raised exception propagates instead of
    # being handed to the model as text. vlm_describe returns None for the
    # outcomes that are findings (a decline, a truncated answer); anything it
    # raises means the call itself did not happen, which is a task failure and
    # not a fact about the paper.
    @function_tool(failure_error_function=None)
    def extract_table_from_image() -> str:
        """Extract the current table image as markdown using vision."""
        image_url = image_to_data_url(image_path)
        content = vlm_describe(image_url, VISION_EXTRACTION_PROMPT)
        # An empty string, never a partial table: the agent reports the table
        # unrecoverable rather than accepting half of one as the extraction.
        return content if content is not None else ''

    return Agent(
        name='table_corrector',
        instructions=TABLE_CORRECTION_INSTRUCTIONS,
        # The vision model, not the extraction model: this agent's whole job is
        # judging a table image, and it must also accept what the vision read
        # returns. On the extraction model (Haiku on dev-caa) it rejected a
        # faithful Fable reading of paper 80's tooth-agenesis chart as
        # unrecoverable.
        model=resolve_model(env.VLM_MODEL),
        model_settings=model_settings_for(env.VLM_MODEL),
        output_type=model_facing_output(TableCorrectionResult),
        tools=[extract_table_from_image],
    )


class TableCorrectionResult(BaseModel):
    """Result of table corruption check and correction."""

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
- Running text (a journal footer, a page header) spliced into cells

A good table has:
- Readable headers describing columns
- Consistent cell alignment
- Content that makes semantic sense

Judging the corrected version: you cannot see the image, so judge the extraction on
its structure, not on whether you can vouch for every cell. Accept it (conversion_successful
true, is_recoverable true, corrected_markdown set to it verbatim) when it is a well-formed
markdown table: a header row, a separator row, data rows, the same number of cells in
every row, and no running text mixed into the cells. A dense grid of +, -, na or U
symbols, a manifestation or pedigree grid, or a table whose rows and columns are the
transpose of the markdown you were given is a normal outcome of reading the image, not a
reason to reject it. Reject it (conversion_successful false, is_recoverable false,
corrected_markdown null) only when it is not a markdown table at all, is mostly empty, is
visibly a fragment (far fewer cells than the markdown you were given), or is prose saying
the table could not be read. Never edit, complete or invent cells yourself: the extraction
is returned as it came or not at all. A rejection is an acceptable outcome, not a failure --
the original markdown will simply be left in place."""


def is_well_formed_table(markdown: str) -> bool:
    """A header row, a separator row and at least one data row, every row
    with the header's number of cells. The structural test behind the judge's
    acceptance, applied in code as well: the judge has no view of the image,
    so structure is all either of them can check, and an extraction that
    passes it is kept whatever the table is a grid of."""
    rows = [line.strip() for line in markdown.strip().splitlines() if line.strip()]
    if len(rows) < 3:
        return False
    cells = [row.strip('|').split('|') for row in rows]
    width = len(cells[0])
    if not all(re.fullmatch(r'\s*:?-+:?\s*', cell) for cell in cells[1]):
        return False
    return all(len(row) == width for row in cells)


async def correct_tables(paper_id: int, supplement: bool = False) -> None:
    """Correct corrupted table markdown in paper using agent.

    Scans all tables and checks each with the agent. The verdict is recorded
    as one of two presence files beside the table: ``N.vision.md`` (corrupt
    and rebuilt from the image -- the rebuilt markdown) or ``N.unrecovered``
    (corrupt and the image did not yield a faithful table); neither means the
    table was clean. ``N.md``, Docling's own reading, is left untouched:
    ``build_anchored`` (``lib.misc.pdf.anchors``) reads the vision file and
    the unrecovered marker when it writes ``anchored.md``, so corrections and
    the warning are applied at build time. N is the Docling table index, the
    same N as the table-N anchor.
    """
    tables_dir = document_tables_dir(paper_id, supplement=supplement)
    if not tables_dir.exists():
        return

    # Find all .md table files
    table_files = sorted(tables_dir.glob('*.md'))
    if not table_files:
        return

    for table_path in table_files:
        # Skip vision files
        if '.vision' in table_path.name:
            continue

        table_id = int(table_path.stem)
        table_markdown = table_path.read_text()

        logger.info(f'Checking table {table_id} for corruption...')

        image_path = document_table_image_path(
            paper_id, table_id, supplement=supplement
        )
        agent = table_correction_agent_for_image(image_path)

        # Build prompt with table markdown only. The vision tool reads the image
        # on demand if the agent decides the markdown is corrupted.
        message = (
            f'Table ID: {table_id}\n\nMarkdown to evaluate:\n```\n{table_markdown}\n```'
        )

        unrecovered_path = document_table_unrecovered_path(
            paper_id, table_id, supplement=supplement
        )

        try:
            result = await Runner.run(agent, message, max_turns=JUDGE_MAX_TURNS)
        except (MaxTurnsExceeded, ModelDeclined) as exc:
            # The model would not, or could not, give a verdict. That is an
            # outcome this step already has a bucket for -- the table is left
            # as parsed and marked unrecovered, so anchored.md carries the
            # warning -- and not a reason to fail the paper's parse, which is
            # what a propagated exception does. ModelDeclined is the provider's
            # safety classifier refusing the judge call (model_factory says how
            # a refusal otherwise becomes MaxTurnsExceeded); MaxTurnsExceeded
            # here is the same thing seen through a model whose adapter did
            # not surface it, or a judge that lost its way, and in either
            # case asking the same question again gets the same answer.
            logger.warning(
                f'Table {table_id}: no verdict from the judge ({exc}); leaving '
                f'the original markdown in place and marking it unrecovered'
            )
            unrecovered_path.touch()
            continue

        if not result.final_output.is_corrupted:
            logger.info(f'Table {table_id} looks OK')
            unrecovered_path.unlink(missing_ok=True)
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
            unrecovered_path.touch()
            continue

        if not is_well_formed_table(result.final_output.corrected_markdown):
            logger.warning(
                f'Table {table_id}: the judge accepted an extraction that is not '
                f'a well-formed markdown table; leaving original markdown in place'
            )
            unrecovered_path.touch()
            continue

        logger.info(f'Table {table_id} was corrupted, corrected version ready')

        # Write vision file
        vision_path = document_table_vision_markdown_path(
            paper_id, table_id, supplement=supplement
        )
        vision_path.write_text(result.final_output.corrected_markdown)
        logger.info(f'Wrote {vision_path}')
        unrecovered_path.unlink(missing_ok=True)
