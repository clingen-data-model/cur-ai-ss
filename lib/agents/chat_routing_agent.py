from pydantic import BaseModel

from agents import Agent

from lib.core.environment import env


class ChatRoutingOutput(BaseModel):
    task_id: int
    reasoning: str


CHAT_ROUTING_INSTRUCTIONS = """
You are a routing assistant for a genetic research paper analysis system.

You will be given:
1. A user's question about a paper
2. A list of completed extraction tasks, each with an id, type, and description

Your job is to pick the single task whose subject matter most closely matches the question.
Return the task_id of the best match and a brief reasoning.

Guidelines:
- Match the question topic to the task type (e.g. questions about variants → Variant Extraction, about patients → Patient Extraction, about phenotypes → HPO Linking, about the paper itself → Paper Metadata)
- If multiple tasks could apply, pick the most specific one
- Always return a valid task_id from the list provided
"""

agent = Agent(
    name='chat_router',
    instructions=CHAT_ROUTING_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=ChatRoutingOutput,
)
