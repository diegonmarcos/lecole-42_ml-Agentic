"""Provider abstraction layer for LLM services"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional


@dataclass
class LLMResponse:
    """Standard LLM response format"""

    content: str
    usage: Dict[str, int]  # {'prompt_tokens': int, 'completion_tokens': int}
    model: str
    finish_reason: str = "stop"


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """Generate chat completion"""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is healthy"""

    @abstractmethod
    def get_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD"""

    @abstractmethod
    async def stream_completion(
        self, model: str, messages: List[Dict[str, str]], **kwargs
    ) -> AsyncIterator[str]:
        """Stream completion chunks"""
        raise NotImplementedError
        yield ""
