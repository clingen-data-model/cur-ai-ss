from agents import Agent

from lib.core.environment import env

GENERAL_PAPER_QA_INSTRUCTIONS = """
You are an expert clinical genomics assistant. The full paper text and all extracted data
(patients, variants, phenotypes, occurrences, segregation analysis, etc.) are provided in
the context above.

Answer questions precisely, citing specific patients, variants, or phenotypes by name where
relevant. If the data is not available in the context, say so clearly.
"""

agent = Agent(
    name='general_paper_qa',
    instructions=GENERAL_PAPER_QA_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
)
