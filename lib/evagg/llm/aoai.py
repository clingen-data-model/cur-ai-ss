import asyncio
import json
import logging
import time
from functools import lru_cache, reduce
from typing import Any, Dict, Iterable, List, Optional

import openai
from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai.types.responses import (
    EasyInputMessageParam,
)
from pydantic import BaseModel

from lib.evagg.prompts import PROMPT_REGISTRY
from lib.evagg.utils.cache import ObjectCache
from lib.evagg.utils.logging import PROMPT

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_SETTINGS = {
    "max_output_tokens": 1024,
    "prompt_tag": "observation",
    "temperature": 0.7,
    "top_p": 0.95,
}


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


class OpenAIConfig(BaseModel):
    api_key: str
    deployment: str
    timeout: int = 60
    max_parallel_requests: int = 0


class AzureOpenAIConfig(OpenAIConfig):
    api_version: str
    endpoint: str
    token_provider: Any = None


class OpenAIClient:
    _config: OpenAIConfig
    _use_azure: bool

    def __init__(self, client_class: str, config: Dict[str, Any]) -> None:
        if client_class == "AsyncOpenAI":
            self._use_azure = False
            self._config = OpenAIConfig(**config)
        elif client_class == "AsyncAzureOpenAI":
            self._use_azure = True
            self._config = AzureOpenAIConfig(**config)
        else:
            raise ValueError(f"Unknown client class: {client_class}")

    @property
    def _client(self) -> AsyncOpenAI:
        return self._get_client_instance()

    @lru_cache
    def _get_client_instance(self) -> AsyncOpenAI:
        if self._use_azure:
            assert isinstance(self._config, AzureOpenAIConfig)
            logger.info(
                f"Using AOAI API {self._config.api_version} at {self._config.endpoint}"
                + f" (max_parallel={self._config.max_parallel_requests})."
            )
            if self._config.token_provider:
                return AsyncAzureOpenAI(
                    azure_endpoint=self._config.endpoint,
                    azure_ad_token_provider=self._config.token_provider,
                    api_version=self._config.api_version,
                    timeout=self._config.timeout,
                )
            return AsyncAzureOpenAI(
                azure_endpoint=self._config.endpoint,
                api_key=self._config.api_key,
                api_version=self._config.api_version,
                timeout=self._config.timeout,
            )
        logger.info(
            "Using AsyncOpenAI"
            + f" (max_parallel={self._config.max_parallel_requests})."
        )
        return AsyncOpenAI(
            api_key=self._config.api_key,
            timeout=self._config.timeout,
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
        self, messages: ChatMessages, settings: Dict[str, Any]
    ) -> str:
        prompt_tag = settings.pop("prompt_tag", "prompt")
        prompt_metadata = settings.pop("prompt_metadata", {})
        connection_errors = 0
        rate_limit_errors = 0

        while True:
            try:
                # Pause 1 second if the number of pending chat completions is at the limit.
                if (max_requests := self._config.max_parallel_requests) > 0:
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
            except (openai.APIConnectionError, openai.APITimeoutError) as e:
                if connection_errors > 2:
                    if hasattr(
                        self._config, "endpoint"
                    ) and self._config.endpoint.startswith("http://localhost"):
                        logger.error(
                            "Azure OpenAI API unreachable - have failed to start a local proxy?"
                        )
                    raise
                if connection_errors == 0:
                    logger.warning(f"Connectivity error on {prompt_tag}: {e.message}")
                connection_errors += 1
                await asyncio.sleep(1)

        prompt_metadata["returned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        prompt_metadata["elapsed_time"] = f"{elapsed:.1f} seconds"

        prompt_log = {
            "prompt_tag": prompt_tag,
            "prompt_metadata": prompt_metadata,
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
        prompt_settings: Optional[Dict[str, Any]] = None,
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
            "model": self._config.deployment,
            **(prompt_settings or {}),
        }
        return await self._generate_completion(messages, settings)

    async def prompt_file(
        self,
        prompt_filepath: str,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self.prompt(
            self._load_prompt_file(prompt_filepath),
            params,
            prompt_settings,
        )

    async def prompt_json(
        self,
        prompt_filepath: str,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = await self.prompt_file(
            prompt_filepath=prompt_filepath,
            params=params,
            prompt_settings=prompt_settings,
        )
        try:
            result = json.loads(response)
        except json.decoder.JSONDecodeError:
            logger.error(
                f"Failed to parse response from LLM to {prompt_filepath}: {response}"
            )
            return {}
        return result


class OpenAICacheClient(OpenAIClient):
    def __init__(self, client_class: str, config: Dict[str, Any]) -> None:
        # Don't cache tasks that have errored out.
        self.task_cache = ObjectCache[asyncio.Task](
            lambda t: not t.done() or t.exception() is None
        )
        super().__init__(client_class, config)

    def _create_response(
        self, messages: ChatMessages, settings: Dict[str, Any]
    ) -> asyncio.Task:
        """Create a new task only if no identical non-errored one was already cached."""
        cache_key = hash((messages.content, json.dumps(settings)))
        if task := self.task_cache.get(cache_key):
            return task
        task = super()._create_response(messages, settings)
        self.task_cache.set(cache_key, task)
        return task
