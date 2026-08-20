"""Agent to correct corrupted table markdown using OpenAI vision."""

import io
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from agents import Agent, Runner, function_tool
from openai import OpenAI
from PIL import Image
from pydantic import BaseModel

from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.gcs import upload_and_sign_image, upload_and_sign_image_bytes
from lib.misc.pdf.paths import (
    pdf_table_correction_path,
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


# docling crops a table exactly as it sits on the page, so a table typeset
# sideways yields a sideways crop. The vision model refuses to transcribe those
# ("the text ... is too low-resolution and partially cut off"), and its stated
# reason is unreliable -- the same crop upright reads perfectly. Rather than
# infer the angle, try all four and keep the best.
ROTATIONS = (0, 90, 180, 270)

_SEPARATOR_ROW = re.compile(r'^[\s:|-]+$')


@dataclass
class RotationOutcome:
    """Which rotation the tool settled on, for the on-disk record."""

    rotation: int | None = None


class RotationChoice(BaseModel):
    """Which rotation produced the most faithful transcription."""

    best_rotation: int
    any_usable: bool
    reasoning: str


ROTATION_CHOICE_INSTRUCTIONS = """You are comparing transcriptions of ONE table, each
produced from the same image at a different rotation. Exactly one rotation shows the
table upright; the others are sideways or upside down.

You are also given the original PDF text extraction of that table. Its STRUCTURE is
scrambled -- that is why the table is being re-extracted -- but its CONTENT is real:
the identifiers, notation and numbers in it were genuinely read off the page. Use it as
the reference. The best candidate is the one whose values agree with the reference.

How to judge:
- Check distinctive strings -- identifiers, variant notation (c.*, p.*), frequencies,
  scores -- against the reference. The candidate recovering the most of them, intact
  and unaltered, wins.
- A candidate that invents values the reference does not contain, or that alters digits
  in them, is wrong no matter how tidy it looks.
- Refusals ("too low-resolution", "unable to extract") are unusable.

Do NOT judge on size or neatness. More columns is not better -- a sideways read often
over-splits cells and scores well on appearance while corrupting digits. Paired or
multi-line values within one cell are usually FAITHFUL, not corruption: a subject with
two variants legitimately has two of everything.

Set any_usable to false only if EVERY candidate is a refusal or unusable garble.
Set best_rotation to the rotation label of your pick."""


def _choose_rotation(
    results: dict[int, str], original_markdown: str
) -> RotationChoice | None:
    """Ask the model which rotation transcribed the table best."""
    candidates = '\n\n'.join(
        f'### Rotation {degrees}\n```\n{results[degrees].strip()}\n```'
        for degrees in ROTATIONS
    )

    client = OpenAI(api_key=env.OPENAI_API_KEY)
    completion = client.chat.completions.parse(
        model=env.OPENAI_API_DEPLOYMENT,
        messages=[
            {'role': 'system', 'content': ROTATION_CHOICE_INSTRUCTIONS},
            {
                'role': 'user',
                'content': (
                    f'## Reference (structure scrambled, content real)\n'
                    f'```\n{original_markdown.strip()}\n```\n\n'
                    f'## Candidates\n{candidates}'
                ),
            },
        ],
        response_format=RotationChoice,
    )
    return completion.choices[0].message.parsed


def _table_shape(markdown: str) -> tuple[int, int]:
    """Return (columns, data_rows) for a markdown table, or (0, 0) if absent."""
    rows = [ln.strip() for ln in markdown.splitlines() if ln.strip().startswith('|')]
    data_rows = [r for r in rows if not _SEPARATOR_ROW.match(r)]
    if not data_rows:
        return 0, 0
    columns = max(len(r.strip('|').split('|')) for r in data_rows)
    return columns, len(data_rows) - 1  # first row is the header


def _rotated_png_bytes(image_path: Path, degrees: int) -> bytes:
    """Rotate a table crop in memory. Nothing is written to disk."""
    buffer = io.BytesIO()
    with Image.open(image_path) as image:
        image.rotate(degrees, expand=True).save(buffer, format='PNG')
    return buffer.getvalue()


def _rotated_object_path(image_path: Path, degrees: int) -> str:
    """GCS object path for a rotated crop, mirroring upload_image_to_gcs."""
    try:
        relative = image_path.relative_to(Path(env.CAA_ROOT))
    except ValueError:
        relative = Path(image_path.name)
    return str(relative.with_name(f'{image_path.stem}.rot{degrees}.png'))


def extract_best_rotation(
    image_path: Path, original_markdown: str, outcome: RotationOutcome | None = None
) -> str:
    """Transcribe a table crop, trying all four rotations.

    Uploads every rotation, transcribes each, and returns whichever yields
    the largest well-formed table. Rotations exist only in memory and in the
    upload; none are written to disk. If no rotation produces a usable
    table, the unrotated response is returned so the caller can judge it.
    """
    client = OpenAI(api_key=env.OPENAI_API_KEY)

    def extract(degrees: int) -> tuple[int, str]:
        if degrees == 0:
            image_url = upload_and_sign_image(image_path)
        else:
            image_url = upload_and_sign_image_bytes(
                _rotated_png_bytes(image_path, degrees),
                _rotated_object_path(image_path, degrees),
            )

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
        return degrees, message.choices[0].message.content or ''

    with ThreadPoolExecutor(max_workers=len(ROTATIONS)) as pool:
        results = dict(pool.map(extract, ROTATIONS))

    for degrees in ROTATIONS:
        columns, data_rows = _table_shape(results[degrees])
        logger.info(f'Rotation {degrees}: {columns} columns, {data_rows} data rows')

    choice = _choose_rotation(results, original_markdown)

    if choice is None or not choice.any_usable or choice.best_rotation not in results:
        logger.warning(
            'No rotation yielded a usable table'
            + (f' ({choice.reasoning})' if choice else '')
        )
        return results[0]

    logger.info(f'Using rotation {choice.best_rotation}: {choice.reasoning}')
    if outcome is not None:
        outcome.rotation = choice.best_rotation
    # Return the chosen candidate verbatim -- never a model's re-rendering of it.
    return results[choice.best_rotation]


def table_correction_agent_for_image(
    image_path: Path, table_markdown: str, outcome: RotationOutcome | None = None
) -> Agent:
    """Build a table correction agent bound to a specific table image."""

    @function_tool
    def extract_table_from_image() -> str:
        """Extract the current table image as markdown using vision.

        Every rotation of the crop is tried; the best-reading one wins.
        """
        return extract_best_rotation(image_path, table_markdown, outcome)

    return Agent(
        name='table_corrector',
        instructions=TABLE_CORRECTION_INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=TableCorrectionResult,
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

A good table has:
- Readable headers describing columns
- Consistent cell alignment
- Content that makes semantic sense

Set conversion_successful to true only if the corrected_markdown is a valid markdown table
with proper pipe delimiters and header rows. If extraction failed or returned invalid
markdown, set it to false.

The extraction tool already tries all four page rotations and returns the best result, so
never decline merely because the table looked sideways or upside down in the markdown.

Some tables cannot be faithfully recovered at all -- for example, dense matrices of tiny
symbols (+/-/*), pedigree/manifestation grids, or images where the cell structure is
genuinely ambiguous. Do not invent or hallucinate content for these. If the table is
corrupted and the image does not yield a faithful, trustworthy markdown table, set
is_recoverable to false and conversion_successful to false. This is an acceptable outcome,
not a failure -- the original markdown will simply be left in place."""


def _write_correction_record(
    paper_id: int,
    table_id: int,
    result: TableCorrectionResult,
    rotation: int | None,
    corrected: bool,
    supplement: bool = False,
) -> None:
    """Persist what was decided about one table, so it is not only a log line."""
    record = {
        'table_id': table_id,
        'is_corrupted': result.is_corrupted,
        'conversion_successful': result.conversion_successful,
        'is_recoverable': result.is_recoverable,
        'corrected': corrected,
        'rotation': rotation,
    }
    path = pdf_table_correction_path(paper_id, table_id, supplement=supplement)
    path.write_text(json.dumps(record, indent=2))


async def correct_tables(paper_id: int, supplement: bool = False) -> None:
    """Correct corrupted table markdown in paper using agent.

    Scans all tables, checks each with the agent, and writes a .vision.md
    beside every table it recovers. ``raw.md`` is deliberately left untouched:
    corrections are applied at read time by
    ``lib.misc.pdf.paths.apply_table_corrections``.
    """
    tables_dir = pdf_tables_dir(paper_id, supplement=supplement)
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

        image_path = pdf_table_image_path(paper_id, table_id, supplement=supplement)
        outcome = RotationOutcome()
        agent = table_correction_agent_for_image(image_path, table_markdown, outcome)

        # Build prompt with table markdown only. The vision tool reads the image
        # on demand if the agent decides the markdown is corrupted.
        message = (
            f'Table ID: {table_id}\n\nMarkdown to evaluate:\n```\n{table_markdown}\n```'
        )

        # Run agent
        result = await Runner.run(agent, message)

        if not result.final_output.is_corrupted:
            logger.info(f'Table {table_id} looks OK')
            _write_correction_record(
                paper_id,
                table_id,
                result.final_output,
                outcome.rotation,
                corrected=False,
                supplement=supplement,
            )
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
            _write_correction_record(
                paper_id,
                table_id,
                result.final_output,
                outcome.rotation,
                corrected=False,
                supplement=supplement,
            )
            continue

        logger.info(f'Table {table_id} was corrupted, corrected version ready')

        # Write vision file
        vision_path = pdf_table_vision_markdown_path(
            paper_id, table_id, supplement=supplement
        )
        vision_path.write_text(result.final_output.corrected_markdown)
        logger.info(f'Wrote {vision_path}')
        _write_correction_record(
            paper_id,
            table_id,
            result.final_output,
            outcome.rotation,
            corrected=True,
            supplement=supplement,
        )
