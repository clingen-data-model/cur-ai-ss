from agents import Agent

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env

GENERAL_PAPER_QA_INSTRUCTIONS = """Answer questions precisely, citing specific patients, variants, or phenotypes by name where relevant. If the data is not available in the context, say so clearly."""

GENERAL_PAPER_QA_AGENT_INSTRUCTIONS = GENERAL_PAPER_QA_INSTRUCTIONS

agent = Agent(
    name='general_paper_qa',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
)
