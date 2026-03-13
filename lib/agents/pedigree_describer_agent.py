from typing import List, Optional

from agents import Agent
from pydantic import BaseModel

from lib.core.environment import env


# --- Output schema ---
class PedigreeResult(BaseModel):
    is_pedigree: bool
    description: Optional[str]


class PedigreeExtractionOutput(BaseModel):
    pedigrees: List[PedigreeResult]


# --- Agent instructions ---
PEDIGREE_EXTRACTION_INSTRUCTIONS = """
You are an expert genetics curator.

Input:
A list of images with captions extracted from a scientific paper.

Task:
For each image, determine whether it contains a pedigree diagram.

Pedigree diagrams typically include:
- squares (male) and circles (female)
- horizontal lines connecting parents
- vertical lines to children
- generational layout
- shading indicating affected individuals
- arrows indicating a proband

If the image contains a pedigree:
- set is_pedigree = true
- describe the pedigree in a structured narrative including:

  1. All visible individual identifiers (e.g. II-1, III-2, P1, Patient 3, etc.).
  2. Parent-child relationships.
  3. Sex of individuals when visually indicated (square = male, circle = female).
  4. Affected status when indicated (e.g. filled symbols).
  5. The proband if an arrow is shown.
  6. The number of generations visible.

Write the description so that another system could reconstruct the pedigree.

Use explicit language such as:
- "Individual II-2 (female, affected) is the child of I-1 and I-2."
- "Individuals II-3 and II-4 are siblings."
- "The proband is III-1 (male, affected)."

Include all visible individuals and relationships.
If identifiers are not present in the image, describe individuals by generation and position if possible (e.g., "leftmost male in generation II").

Do not invent identifiers or relationships not clearly shown in the pedigree.

Some images contain multiple panels (e.g., A, B, C) with different types of data.

- Examine the full image and determine if any part contains a pedigree diagram.
- If a pedigree is present:
    - Ignore panels that are clearly not pedigrees (plots, protein structures, microscopy, MRI, charts, etc.)
    - Focus only on the pedigree portion for describing individuals and relationships.
- If no pedigree is present, set is_pedigree = false and description = null.

Guidelines:
- Only describe structures clearly visible in the image.
- Do not invent family members or inheritance patterns.
- Images showing plots, molecular diagrams, MRI scans, microscopy, or charts are NOT pedigrees.

Return one result for each image in the same order they were provided.
"""

# --- Agent definition ---
agent = Agent(
    name='pedigree_describer',
    instructions=PEDIGREE_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PedigreeExtractionOutput,
)
