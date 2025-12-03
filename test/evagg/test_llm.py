import os
from functools import reduce
from unittest.mock import AsyncMock, patch


from openai import AsyncAzureOpenAI

from lib.evagg.llm import OpenAIClient


@patch("lib.evagg.llm.aoai.AsyncAzureOpenAI", return_value=AsyncMock())
async def test_openai_client_prompt(
    mock_openai, test_file_contents, test_resources_path
) -> None:
    prompt_template = test_file_contents("phenotype.txt")
    prompt_params = {"gene": "GENE", "variant": "VARIANT", "passage": "PASSAGE"}
    prompt_text = reduce(
        lambda x, kv: x.replace(f"{{{{${kv[0]}}}}}", kv[1]),
        prompt_params.items(),
        prompt_template,
    )
    mock_openai.return_value.chat.completions.create.return_value.choices[
        0
    ].message.content = "response"
    client = OpenAIClient(
        "AsyncAzureOpenAI",
        {
            "deployment": "gpt-8",
            "endpoint": "https://ai",
            "api_key": "test",
            "api_version": "test",
            "timeout": 60,
        },
    )
    response = await client.prompt_file(
        prompt_filepath=os.path.join(test_resources_path, "phenotype.txt"),
        params=prompt_params,
        prompt_settings={"temperature": 1.5, "prompt_tag": "phenotype"},
    )
    assert response == "response"
    mock_openai.assert_called_once_with(
        azure_endpoint="https://ai", api_key="test", api_version="test", timeout=60
    )
    mock_openai.return_value.chat.completions.create.assert_called_once_with(
        messages=[
            {
                "role": "system",
                "content": "You are an intelligent assistant to a genetic analyst. Their task is to identify the genetic variant or variants that\nare causing a patient's disease. One approach they use to solve this problem is to seek out evidence from the academic\nliterature that supports (or refutes) the potential causal role that a given variant is playing in a patient's disease.\n\nAs part of that process, you will assist the analyst in collecting specific details about genetic variants that have\nbeen observed in the literature.\n\nAll of your responses should be provided in the form of a JSON object. These responses should never include long,\nuninterrupted sequences of whitespace characters.",
            },
            {"role": "user", "content": prompt_text},
        ],
        max_tokens=1024,
        frequency_penalty=0,
        presence_penalty=0,
        temperature=1.5,
        top_p=0.95,
        response_format={"type": "json_object"},
        model="gpt-8",
    )
