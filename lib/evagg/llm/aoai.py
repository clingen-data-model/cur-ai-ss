import asyncio
import json
import logging
import time
from functools import lru_cache, reduce
from typing import Any, Dict, Iterable, List, Optional

import openai
from openai import AsyncOpenAI
from openai.types.responses import (
    EasyInputMessageParam,
)

from lib.evagg.prompts import PROMPT_REGISTRY
from lib.evagg.types import PromptTag
from lib.evagg.utils.environment import env
from lib.evagg.utils.logging import PROMPT

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_SETTINGS = {
    "max_output_tokens": 4096,
}

MAX_PARALLEL_REQUESTS = 5
TIMEOUT_S = 60


class ChatMessages:
    _messages: List[EasyInputMessageParam]

    @property
    def content(self) -> str:
        return "".join([json.dumps(message) for message in self._messages])

    def __init__(self, messages: Iterable[EasyInputMessageParam]) -> None:
        self._messages = list(messages)

    def __hash__(self) -> int:
        return hash(self.content)

    def insert(self, index: int, message: EasyInputMessageParam) -> None:
        self._messages.insert(index, message)

    def to_list(self) -> List[EasyInputMessageParam]:
        return self._messages.copy()


class OpenAIClient:
    @property
    def _client(self) -> AsyncOpenAI:
        return self._get_client_instance()

    @lru_cache
    def _get_client_instance(self) -> AsyncOpenAI:
        logger.info("Using AsyncOpenAI" + f" (max_parallel={MAX_PARALLEL_REQUESTS}).")
        return AsyncOpenAI(
            api_key=env.OPENAI_API_KEY,
            timeout=TIMEOUT_S,
        )

    @lru_cache
    def _load_prompt_file(self, prompt_file: str) -> str:
        with open(prompt_file, "r") as f:
            return f.read()

    def _create_response(
        self, messages: ChatMessages, settings: Dict[str, Any]
    ) -> asyncio.Task:
        """Schedule a completion task to the event loop and return the awaitable."""
        response = self._client.responses.create(
            input=[EasyInputMessageParam(**x) for x in messages.to_list()], **settings
        )
        return asyncio.create_task(response, name="chat")

    async def _generate_completion(
        self,
        messages: ChatMessages,
        prompt_tag: PromptTag,
        settings: Dict[str, Any],
    ) -> str:
        rate_limit_errors = 0
        while True:
            try:
                # Pause 1 second if the number of pending chat completions is at the limit.
                if (max_requests := MAX_PARALLEL_REQUESTS) > 0:
                    while (
                        sum(1 for t in asyncio.all_tasks() if t.get_name() == "chat")
                        > max_requests
                    ):
                        await asyncio.sleep(1)

                start_ts = time.time()
                response = await self._create_response(messages, settings)
                elapsed = time.time() - start_ts
                break
            except (openai.RateLimitError, openai.InternalServerError) as e:
                # Only report the first rate limit error not from a proxy unless it's constant.
                if rate_limit_errors > 10 or (
                    rate_limit_errors == 0
                    and not e.message.startswith("No good endpoints")
                ):
                    logger.warning(f"Rate limit error on {prompt_tag}: {e}")
                rate_limit_errors += 1
                await asyncio.sleep(1)
            except (openai.APIConnectionError, openai.APITimeoutError):
                await asyncio.sleep(1)

        prompt_log = {
            "prompt_tag": prompt_tag,
            "prompt_metadata": {
                "returned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_time": f"{elapsed:.1f} seconds",
            },
            "prompt_settings": settings,
            "prompt_text": "\n".join(
                [str(m.get("content")) for m in messages.to_list()]
            ),
            "prompt_response": response.output_text or "",
            "prompt_response_metadata": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
        }
        logger.log(
            PROMPT,
            f"Chat '{prompt_tag}' complete in {elapsed:.1f} seconds.",
            extra=prompt_log,
        )
        return response.output_text or ""

    async def prompt(
        self,
        user_prompt: str,
        params: Optional[Dict[str, str]] = None,
        prompt_tag: PromptTag = PromptTag.PROMPT,
        settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Get the response from a prompt."""
        # Replace any '{{${key}}}' instances with values from the params dictionary.
        user_prompt = reduce(
            lambda x, kv: x.replace(f"{{{{${kv[0]}}}}}", kv[1]),
            (params or {}).items(),
            user_prompt,
        )

        messages: ChatMessages = ChatMessages(
            [EasyInputMessageParam(role="user", content=user_prompt)]
        )
        messages.insert(
            0,
            EasyInputMessageParam(
                role="system", content=PROMPT_REGISTRY["system"].render_template()
            ),
        )

        settings = {
            **DEFAULT_PROMPT_SETTINGS,
            "model": env.OPENAI_API_DEPLOYMENT,
            **(settings or {}),
        }
        return await self._generate_completion(messages, prompt_tag, settings)

    async def prompt_json_from_string(
        self,
        user_prompt: str,
        params: Optional[Dict[str, str]] = None,
        prompt_tag: PromptTag = PromptTag.PROMPT,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a user string prompt to the LLM and parse the response as JSON.
        Returns an empty dict if parsing fails.
        """
        response = await self.prompt(
            user_prompt=user_prompt,
            params=params,
            prompt_tag=prompt_tag,
            settings=settings,
        )
        try:
            result = json.loads(response)
        except json.decoder.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON: {response}")
            return {}
        return result

    async def prompt_file(
        self,
        prompt_filepath: str,
        params: Optional[Dict[str, str]] = None,
        prompt_tag: PromptTag = PromptTag.PROMPT,
        settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self.prompt(
            self._load_prompt_file(prompt_filepath),
            params,
            prompt_tag,
            settings,
        )

    async def prompt_json(
        self,
        prompt_filepath: str,
        params: Optional[Dict[str, str]] = None,
        prompt_tag: PromptTag = PromptTag.PROMPT,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = await self.prompt_file(
            prompt_filepath=prompt_filepath,
            params=params,
            prompt_tag=prompt_tag,
            settings=settings,
        )
        try:
            result = json.loads(response)
        except json.decoder.JSONDecodeError:
            logger.error(
                f"Failed to parse response from LLM to {prompt_filepath}: {response}"
            )
            return {}
        return result
