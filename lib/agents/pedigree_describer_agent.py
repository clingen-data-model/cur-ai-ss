from typing import Optional

from agents import Agent, function_tool
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env
from lib.misc.gcs import upload_and_sign_image
from lib.misc.pdf.paths import pdf_image_path


# --- Output schema ---
class PedigreeExtractionOutput(BaseModel):
    found: bool
    image_id: Optional[int] = None
    description: Optional[str] = None


def _analyze_image_url(image_url: str) -> str:
    """Run the vision model against an image URL and return its description."""
    from openai import OpenAI

    client = OpenAI(api_key=env.OPENAI_API_KEY)

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
                        'text': """First determine whether this image is a pedigree (family tree) diagram.
If it is NOT a pedigree diagram, respond with exactly NOT_A_PEDIGREE and nothing else.

Otherwise, extract detailed pedigree information from this diagram.

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

IMPORTANT: List every visible individual, even if some details are unclear. Do not infer missing details.""",
                    },
                ],
            }
        ],
    )

    content = message.choices[0].message.content
    return content if content is not None else ''


# --- Agent instructions ---
PEDIGREE_EXTRACTION_INSTRUCTIONS = """
INPUT: A list of figures, each with an image_id, whether it is a supplement figure, and a caption.

Task Overview
-------------
Determine whether any figure contains a pedigree diagram, and if so, extract detailed pedigree information.

PROCESS
-------
You MUST evaluate the actual image to decide — never decide from the caption alone.
For each figure, call analyze_pedigree_image with its image_id and is_supplement flag.
The tool loads the image and either returns detailed pedigree information or the literal
string NOT_A_PEDIGREE.

Stop as soon as the tool confirms a pedigree, or once every figure has been evaluated and
none are pedigrees.

DECISION:
- If the tool returned pedigree details for a figure: set found=True, and populate image_id
  and description from that tool output.
- If the tool returned NOT_A_PEDIGREE for every figure: set found=False, image_id=None,
  description=None.

IMPORTANT GUARDRAILS:
- The tool's visual verdict is authoritative — do not report found=True without a tool
  response that actually contains pedigree details (not NOT_A_PEDIGREE).
- found=True even if resolution is low or some details are unclear (the tool handles
  incomplete clarity, and will still return details rather than NOT_A_PEDIGREE).
"""


# --- Agent instructions ---
PEDIGREE_DESCRIBER_AGENT_INSTRUCTIONS = PEDIGREE_EXTRACTION_INSTRUCTIONS


def pedigree_describer_agent_for_paper(paper_id: int) -> Agent:
    """Build a pedigree describer agent bound to a specific paper's images."""

    @function_tool
    def analyze_pedigree_image(image_id: int, is_supplement: bool = False) -> str:
        """Evaluate a figure's image to determine whether it is a pedigree.

        Identify the image by its image_id and is_supplement flag (as listed in the
        input). Returns a detailed analysis of individuals, relationships, and
        inheritance patterns if the image is a pedigree, or the literal string
        NOT_A_PEDIGREE if it is not.
        """
        image_path = pdf_image_path(paper_id, image_id, supplement=is_supplement)
        return _analyze_image_url(upload_and_sign_image(image_path))

    return Agent(
        name='pedigree_describer',
        instructions=BASE_SYSTEM_INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=PedigreeExtractionOutput,
        tools=[analyze_pedigree_image],
    )
