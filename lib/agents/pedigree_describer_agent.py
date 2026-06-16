from typing import Optional

from agents import Agent, function_tool
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env


# --- Output schema ---
class PedigreeExtractionOutput(BaseModel):
    found: bool
    image_id: Optional[int] = None
    description: Optional[str] = None


# --- Vision tool (guardrailed by agent) ---
@function_tool
def analyze_pedigree_image(image_url: str) -> str:
    """Analyze a pedigree image with high detail to extract comprehensive description.

    Only call this tool AFTER confirming the image contains a pedigree diagram.
    Returns detailed analysis of individuals, relationships, and inheritance patterns.
    """
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
                        'text': """Extract detailed pedigree information from this diagram.

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
INPUT: Image URLs with captions

Task Overview
-------------
Determine whether any image contains a pedigree diagram, and if so, extract detailed pedigree information.

TWO-STEP PROCESS:

STEP 1 — IDENTIFY PEDIGREE (examine URLs and captions)
-------------------------------------------------------
Review the provided image URLs and their captions to determine if a pedigree diagram is present.
A pedigree typically has keywords like: pedigree, family tree, family history, hereditary pattern, inheritance, etc.

Decision:
- If NO pedigree exists: Set found=False, image_id=None, description=None. STOP.
- If a pedigree exists (confirmed in Step 1): Proceed to Step 2.

STEP 2 — EXTRACT DETAILS (use analyze_pedigree_image tool)
-----------------------------------------------------------
ONLY if you confirmed a pedigree in Step 1, call analyze_pedigree_image with the image_url.
The tool will return detailed pedigree information.

Set found=True and populate image_id and description from the tool output.

IMPORTANT GUARDRAILS:
- Only call analyze_pedigree_image if you confirmed a pedigree exists
- found=False with None values ONLY when no pedigree diagram is present
- found=True even if resolution is low or some details are unclear (the tool handles incomplete clarity)
"""


# --- Agent definition ---
PEDIGREE_DESCRIBER_AGENT_INSTRUCTIONS = PEDIGREE_EXTRACTION_INSTRUCTIONS

agent = Agent(
    name='pedigree_describer',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PedigreeExtractionOutput,
    tools=[analyze_pedigree_image],
)
