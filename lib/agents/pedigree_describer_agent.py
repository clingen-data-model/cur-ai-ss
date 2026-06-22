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
INPUT: A list of images, each labeled `[Image N]` (N is an integer) with a caption.

Task Overview
-------------
Determine whether any image contains a pedigree diagram, and if so, extract detailed pedigree information.

TWO-STEP PROCESS:

STEP 1 — IDENTIFY PEDIGREE (examine the image labels and captions)
-------------------------------------------------------------------
Review the provided image captions to determine if a pedigree diagram is present.
A pedigree typically has keywords like: pedigree, family tree, family history, hereditary pattern, inheritance, etc.

Decision:
- If NO pedigree exists: Set found=False, image_id=None, description=None. STOP.
- If a pedigree exists (confirmed in Step 1): Proceed to Step 2.

STEP 2 — EXTRACT DETAILS (use analyze_pedigree_image tool)
-----------------------------------------------------------
ONLY if you confirmed a pedigree in Step 1, call analyze_pedigree_image with the integer N
from that image's `[Image N]` label. The tool will return detailed pedigree information.

Set found=True, set image_id to that same integer N, and populate description from the tool output.

IMPORTANT GUARDRAILS:
- Only call analyze_pedigree_image if you confirmed a pedigree exists
- Pass the integer image reference (N), not a URL or filename
- found=False with None values ONLY when no pedigree diagram is present
- found=True even if resolution is low or some details are unclear (the tool handles incomplete clarity)
"""


# --- Agent definition ---
PEDIGREE_DESCRIBER_AGENT_INSTRUCTIONS = PEDIGREE_EXTRACTION_INSTRUCTIONS


def pedigree_describer_agent_for_images(image_map: dict[int, Path]) -> Agent:
    """Build a pedigree describer agent bound to a set of candidate images.

    The agent receives only integer image references in its prompt; the vision
    tool resolves each reference to a local image path here, so the image URL
    (a potentially large base64 data URL in local dev) never crosses the model
    boundary as prompt text or a tool argument.

    Args:
        image_map: Mapping of image reference (int) to the local image path.
    """

    @function_tool
    def analyze_pedigree_image(image_ref: int) -> str:
        """Analyze a pedigree image with high detail to extract a comprehensive description.

        Only call this tool AFTER confirming the image contains a pedigree diagram.
        Returns detailed analysis of individuals, relationships, and inheritance patterns.

        Args:
            image_ref: The integer N from the image's `[Image N]` label.

        Returns:
            Detailed analysis of individuals, relationships, and inheritance patterns.
        """
        image_path = image_map.get(image_ref)
        if image_path is None:
            valid = ', '.join(str(k) for k in sorted(image_map)) or 'none'
            return f'No image with reference {image_ref}; valid references: {valid}'

        return describe_image(image_path, PEDIGREE_VISION_PROMPT)

    return Agent(
        name='pedigree_describer',
        instructions=BASE_SYSTEM_INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=PedigreeExtractionOutput,
        tools=[analyze_pedigree_image],
    )
