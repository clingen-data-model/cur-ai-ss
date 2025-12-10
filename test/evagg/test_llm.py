import os
from functools import reduce
from unittest.mock import AsyncMock, patch


from lib.evagg.llm import OpenAIClient
from lib.evagg.types import PromptTag


@patch("lib.evagg.llm.aoai.AsyncOpenAI", return_value=AsyncMock())
async def test_openai_client_prompt(
    mock_openai, test_file_contents, test_resources_path, caplog
) -> None:
    prompt_template = test_file_contents("phenotype.txt")
    prompt_params = {"gene": "GENE", "variant": "VARIANT", "passage": "PASSAGE"}
    prompt_text = reduce(
        lambda x, kv: x.replace(f"{{{{${kv[0]}}}}}", kv[1]),
        prompt_params.items(),
        prompt_template,
    )
    mock_openai.return_value.responses.create.return_value.output_text = "response"
    client = OpenAIClient()
    response = await client.prompt_file(
        prompt_filepath=os.path.join(test_resources_path, "phenotype.txt"),
        params=prompt_params,
        prompt_tag=PromptTag.PHENOTYPES_ALL,
    )
    assert response == "response"
    mock_openai.assert_called_once_with(api_key="test_api_key", timeout=60)
    mock_openai.return_value.responses.create.assert_called_once_with(
        input=[
            {
                "role": "system",
                "content": "You are an intelligent assistant to a genetic analyst. Their task is to identify the genetic variant or variants that\nare causing a patient's disease. One approach they use to solve this problem is to seek out evidence from the academic\nliterature that supports (or refutes) the potential causal role that a given variant is playing in a patient's disease.\n\nAs part of that process, you will assist the analyst in collecting specific details about genetic variants that have\nbeen observed in the literature.\n\nAll of your responses should be provided in the form of a JSON object. These responses should never include long,\nuninterrupted sequences of whitespace characters.  Do not return the JSON with MarkDown fences (e.g., ```json ... ```).",
            },
            {"role": "user", "content": prompt_text},
        ],
        max_output_tokens=1024,
        model="gpt-8",
    )
    assert (
        "Level 55 lib.evagg.llm.aoai:aoai.py:125 Chat 'PromptTag.PHENOTYPES_ALL' complete in 0.0 seconds."
        in caplog.text
    )
