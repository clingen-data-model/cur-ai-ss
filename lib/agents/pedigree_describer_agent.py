from typing import Optional

from agents import Agent
from pydantic import BaseModel

from lib.core.environment import env


# --- Output schema ---
class PedigreeExtractionOutput(BaseModel):
    found: bool
    image_id: Optional[int] = None
    description: Optional[str] = None


# --- Agent instructions ---
PEDIGREE_EXTRACTION_INSTRUCTIONS = """
Task Overview
-------------
Determine whether any image contains a pedigree diagram.

If NO pedigree exists:
- Set found=False, image_id=None, description=None.

If a pedigree exists:
- Set found=True and proceed:

1. Identify the best pedigree image.
2. Enumerate all individuals.
3. Verify completeness.
4. Write the pedigree description.

Step 1 — Identify the best pedigree image and all individuals
---------------------------------
Scan the pedigree and list EVERY individual visible.

Record:
- identifier (if present)
- generation
- left-to-right position
- sex
- affected status

Example:
1. I-1 (male, unaffected)
2. I-2 (female, unaffected)
3. II-1 (male, affected)
4. II-2 (female, unaffected)

If identifiers are not present, use positional labels.

Large pedigrees may contain 20–40 individuals.
You MUST list every visible individual.

Step 2 — Completeness check
---------------------------
Verify that every square or circle in the pedigree
has been included in the list.

If any were missed, add them.

Step 3 — Pedigree description
-----------------------------
Using the list from Step 1, describe:

- parent-child relationships
- sibling groups
- affected individuals
- the proband if present
- number of generations

IMPORTANT: Always set found=True and populate both image_id and description when a pedigree is found. Set found=False with None values when no pedigree is found.
"""


# --- Agent definition ---
agent = Agent(
    name='pedigree_describer',
    instructions=PEDIGREE_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PedigreeExtractionOutput,
)
