"""
Shared implementation for providers that expose an OpenAI-compatible API.

OpenAI, Together AI, Fireworks AI and Jan all speak the same
``/chat/completions`` + ``/models`` protocol; subclasses only declare their
pricing, defaults and authentication settings.
"""

import json
import os
from typing import AsyncIterator, Dict, List, Optional, Tuple

import aiohttp

from .base import LLMProvider, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    """Base class for OpenAI-compatible chat completion APIs."""

    # Human-readable provider name (used in error messages)
    DISPLAY_NAME = "OpenAI-compatible"
    # Environment variable holding the API key (None = no authentication)
    API_KEY_ENV: Optional[str] = None
    # Path prefix inserted between base_url and the endpoint (e.g. "/v1")
    API_PREFIX = ""
    # Extra fields always sent with non-streaming completions
    EXTRA_COMPLETION_FIELDS: Dict[str, object] = {}
    # Pricing per 1M tokens (input, output)
    PRICING: Dict[str, Tuple[float, float]] = {}
    DEFAULT_MODEL = ""
    DEFAULT_PRICING: Tuple[float, float] = (0.0, 0.0)

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """
        Initialize the provider.

        Args:
            base_url: API base URL
            api_key: API key (falls back to the API_KEY_ENV environment variable)

        Raises:
            ValueError: If the provider requires a key and none is available
        """
        self.api_key: Optional[str] = None
        if self.API_KEY_ENV:
            self.api_key = api_key or os.getenv(self.API_KEY_ENV)
            if not self.api_key:
                raise ValueError(
                    f"{self.DISPLAY_NAME} API key required "
                    f"(set {self.API_KEY_ENV} env var)"
                )

        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    def _url(self, endpoint: str) -> str:
        """Build the full URL for an API endpoint."""
        return f"{self.base_url}{self.API_PREFIX}{endpoint}"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers = {"Authorization": f"Bearer {self.api_key}", **headers}
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate a chat completion.

        Args:
            model: Model name
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Max tokens to generate
            stream: Whether to stream response (not used for non-streaming)
            **kwargs: Additional API parameters (top_p, etc.)

        Returns:
            LLMResponse with content, usage, model, finish_reason

        Raises:
            aiohttp.ClientError: On network/API errors
        """
        session = await self._get_session()

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **self.EXTRA_COMPLETION_FIELDS,
            **kwargs,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with session.post(self._url("/chat/completions"), json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            model=data.get("model", model),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def stream_completion(
        self, model: str, messages: List[Dict[str, str]], **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream completion chunks (server-sent events).

        Args:
            model: Model name
            messages: List of message dicts
            **kwargs: Additional API parameters

        Yields:
            Content chunks as they arrive
        """
        session = await self._get_session()

        payload = {"model": model, "messages": messages, "stream": True, **kwargs}

        async with session.post(self._url("/chat/completions"), json=payload) as resp:
            resp.raise_for_status()

            async for raw_line in resp.content:
                line = raw_line.decode("utf-8").strip()

                if not line or line == "data: [DONE]":
                    continue

                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        delta = data["choices"][0].get("delta", {})

                        if "content" in delta:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError):
                        continue

    async def health_check(self) -> bool:
        """
        Check if the API is reachable (via the /models endpoint).

        Returns:
            True if API is reachable and credentials are valid
        """
        try:
            session = await self._get_session()

            async with session.get(
                self._url("/models"), timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200

        except Exception:  # pylint: disable=broad-exception-caught
            return False

    def get_cost(
        self, input_tokens: int, output_tokens: int, model: Optional[str] = None
    ) -> float:
        """
        Calculate cost in USD for token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name (defaults to DEFAULT_MODEL)

        Returns:
            Cost in USD
        """
        input_price, output_price = self.PRICING.get(
            model or self.DEFAULT_MODEL, self.DEFAULT_PRICING
        )

        # Prices are per 1M tokens
        return (input_tokens * input_price / 1_000_000) + (
            output_tokens * output_price / 1_000_000
        )

    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
