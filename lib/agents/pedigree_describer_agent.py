from pathlib import Path
from typing import Optional

from agents import Agent, function_tool
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.vision import describe_image
from lib.core.environment import env


# --- Output schema ---
class PedigreeExtractionOutput(BaseModel):
    found: bool
    image_id: Optional[int] = None
    is_supplement: bool = False
    description: Optional[str] = None


# --- Vision prompt used when analyzing a confirmed pedigree image ---
PEDIGREE_VISION_PROMPT = """Extract detailed pedigree information from this diagram.

For the pedigree shown, enumerate ALL individuals visible, even if unclear or low resolution:
- Identifier (if present)
- Generation
- Left-to-right position
- Sex (if discernible, otherwise mark uncertain)
- Affected status (if discernible, otherwise mark uncertain)

Then describe:
- Parent-child relationships
- Sibling groups
- Affected individuals
- The proband if present
- Number of generations
- Any uncertainties due to image resolution or clarity

IMPORTANT: List every visible individual, even if some details are unclear. Do not infer missing details."""


# --- Agent instructions ---
PEDIGREE_EXTRACTION_INSTRUCTIONS = """
INPUT: A list of images with captions. Main-paper images are labeled `[Image N]`; supplement
images are labeled `[Supplement Image N]`. N is always the per-source integer index.

Task Overview
-------------
Determine whether any image contains a pedigree diagram, and if so, extract detailed pedigree information.

TWO-STEP PROCESS:

STEP 1 — IDENTIFY PEDIGREE (examine the image labels and captions)
-------------------------------------------------------------------
Review the provided image captions to determine if a pedigree diagram is present.
A pedigree typically has keywords like: pedigree, family tree, family history, hereditary pattern, inheritance, etc.

Decision:
- If NO pedigree exists: Set found=False, image_id=None, is_supplement=False, description=None. STOP.
- If a pedigree exists (confirmed in Step 1): Proceed to Step 2.

STEP 2 — EXTRACT DETAILS (use analyze_pedigree_image tool)
-----------------------------------------------------------
ONLY if you confirmed a pedigree in Step 1, call analyze_pedigree_image with:
- image_id=N (the integer from the label)
- is_supplement=False if the label was `[Image N]`, or is_supplement=True if it was `[Supplement Image N]`

The tool will return detailed pedigree information.

Set found=True, set image_id=N and is_supplement to match the label type, and populate description
from the tool output.

IMPORTANT GUARDRAILS:
- Only call analyze_pedigree_image if you confirmed a pedigree exists
- Pass the integer N from the label, not a URL or filename
- found=False with None/False values ONLY when no pedigree diagram is present
- found=True even if resolution is low or some details are unclear (the tool handles incomplete clarity)
"""


# --- Agent definition ---
PEDIGREE_DESCRIBER_AGENT_INSTRUCTIONS = PEDIGREE_EXTRACTION_INSTRUCTIONS


def pedigree_describer_agent_for_images(
    image_map: dict[int, Path],
    supplement_image_map: dict[int, Path],
) -> Agent:
    """Build a pedigree describer agent bound to a set of candidate images.

    The agent receives only integer image ids in its prompt; the vision tool resolves
    each id + is_supplement flag to a local image path here, so the image URL (a
    potentially large base64 data URL in local dev) never crosses the model boundary
    as prompt text or a tool argument.

    Args:
        image_map: Mapping of per-type image_id (int) to path for main-paper images.
        supplement_image_map: Mapping of per-type image_id (int) to path for supplement images.
    """

    @function_tool
    def analyze_pedigree_image(image_id: int, is_supplement: bool = False) -> str:
        """Analyze a pedigree image with high detail to extract a comprehensive description.

        Only call this tool AFTER confirming the image contains a pedigree diagram.
        Returns detailed analysis of individuals, relationships, and inheritance patterns.

        Args:
            image_id: The integer N from the image's label (`[Image N]` or `[Supplement Image N]`).
            is_supplement: True if the label was `[Supplement Image N]`, False if `[Image N]`.

        Returns:
            Detailed analysis of individuals, relationships, and inheritance patterns.
        """
        target_map = supplement_image_map if is_supplement else image_map
        image_path = target_map.get(image_id)
        if image_path is None:
            valid_regular = ', '.join(str(k) for k in sorted(image_map))
            valid_supplement = ', '.join(str(k) for k in sorted(supplement_image_map))
            return (
                f'No image with id={image_id}, is_supplement={is_supplement}; '
                f'valid regular: {valid_regular}; valid supplement: {valid_supplement}'
            )

        return describe_image(image_path, PEDIGREE_VISION_PROMPT)

    return Agent(
        name='pedigree_describer',
        instructions=BASE_SYSTEM_INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=PedigreeExtractionOutput,
        tools=[analyze_pedigree_image],
    )
