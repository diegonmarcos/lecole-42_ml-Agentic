"""Ollama provider implementation (Tier 0/2)"""

import asyncio
import json
from typing import AsyncIterator, Dict, List, Optional

import aiohttp

from .base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider ($0 cost)"""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs,
    ) -> LLMResponse:
        options = kwargs.pop("options", {})
        options.setdefault("temperature", temperature)
        if max_tokens is not None:
            options.setdefault("num_predict", max_tokens)
        kwargs["options"] = options
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False, **kwargs},
        ) as resp:
            data = await resp.json()
            return LLMResponse(
                content=data["message"]["content"],
                usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                },
                model=model,
            )

    async def health_check(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    def get_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0  # Ollama is free

    async def stream_completion(
        self, model: str, messages: List[Dict], **kwargs
    ) -> AsyncIterator[str]:
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/api/chat",
            json={"model": model, "messages": messages, "stream": True, **kwargs},
        ) as resp:
            async for line in resp.content:
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data:
                            yield data["message"].get("content", "")
                    except json.JSONDecodeError:
                        continue
