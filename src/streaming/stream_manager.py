"""
Stream Manager - Streaming LLM responses with early termination

Features:
- Stream LLM responses in real-time
- Early termination based on quality thresholds
- Token-by-token delivery
- Buffer management
- Concurrent stream handling
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from src.providers.router import Tier, build_local_router

logger = logging.getLogger(__name__)


class TerminationReason(Enum):
    """Reason for stream termination"""

    COMPLETE = "complete"
    EARLY_STOP = "early_stop"
    QUALITY_THRESHOLD = "quality_threshold"
    TIMEOUT = "timeout"
    ERROR = "error"
    USER_CANCELLED = "user_cancelled"


@dataclass
class StreamChunk:
    """Streaming chunk"""

    content: str
    chunk_index: int
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamResult:
    """Complete stream result"""

    full_content: str
    chunks: List[StreamChunk]
    termination_reason: TerminationReason
    total_tokens: int
    duration: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class QualityEvaluator:
    """
    Evaluates streaming quality for early termination.

    Checks if the response meets quality thresholds before completion.
    """

    def __init__(
        self,
        min_length: int = 50,
        coherence_threshold: float = 0.7,
        check_interval: int = 20,  # tokens
    ):
        """
        Initialize quality evaluator.

        Args:
            min_length: Minimum acceptable length
            coherence_threshold: Minimum coherence score (0-1)
            check_interval: Check quality every N tokens
        """
        self.min_length = min_length
        self.coherence_threshold = coherence_threshold
        self.check_interval = check_interval

    def should_terminate_early(
        self, accumulated_text: str, token_count: int
    ) -> tuple[bool, Optional[str]]:
        """
        Check if stream should terminate early.

        Args:
            accumulated_text: Text accumulated so far
            token_count: Number of tokens generated

        Returns:
            Tuple of (should_terminate, reason)
        """
        # Check minimum length
        if len(accumulated_text) < self.min_length:
            return False, None

        # Only check at intervals
        if token_count % self.check_interval != 0:
            return False, None

        # Check for completion markers
        completion_markers = [
            "\n\nTask complete",
            "\n\nDone",
            "```\n\nThe above",
            "\n\nIn summary",
        ]

        for marker in completion_markers:
            if marker.lower() in accumulated_text.lower():
                return True, f"Detected completion marker: {marker[:20]}"

        # Check for repetition (sign of poor quality)
        lines = accumulated_text.split("\n")
        if len(lines) > 3:
            # Check last 3 lines for repetition
            recent_lines = lines[-3:]
            if len(set(recent_lines)) == 1:
                return True, "Detected repetitive output"

        return False, None


class StreamManager:
    """
    Manages streaming LLM responses.

    Usage:
        manager = StreamManager()

        async for chunk in manager.stream(
            provider_router=router,
            tier=Tier.LOCAL_FREE,
            model="llama3.1:8b",
            messages=[...],
            quality_check=True
        ):
            print(chunk.content, end="", flush=True)

        result = manager.get_result()
    """

    def __init__(
        self,
        buffer_size: int = 10,
        timeout: float = 60.0,
        enable_quality_check: bool = True,
    ):
        """
        Initialize stream manager.

        Args:
            buffer_size: Maximum chunks to buffer
            timeout: Stream timeout in seconds
            enable_quality_check: Enable quality-based early termination
        """
        self.buffer_size = buffer_size
        self.timeout = timeout
        self.enable_quality_check = enable_quality_check

        self.quality_evaluator = QualityEvaluator()

        # State
        self._current_result: Optional[StreamResult] = None
        self._active_streams: Dict[str, asyncio.Task] = {}

    async def stream(  # pylint: disable=too-many-locals
        self,
        provider_router,
        tier,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = None,
        quality_check: bool = True,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream LLM response.

        Args:
            provider_router: LLM provider router
            tier: LLM tier
            model: Model name
            messages: Message history
            temperature: Sampling temperature
            max_tokens: Max tokens
            stop_sequences: Sequences that trigger early stop
            quality_check: Enable quality checking
            **kwargs: Additional provider arguments

        Yields:
            StreamChunk objects
        """
        start_time = time.time()
        accumulated_text = ""
        chunks = []
        chunk_index = 0
        termination_reason = TerminationReason.COMPLETE

        try:
            # Stream from provider
            async for content_chunk in provider_router.stream_completion(
                tier=tier,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                accumulated_text += content_chunk

                # Create chunk
                chunk = StreamChunk(content=content_chunk, chunk_index=chunk_index)
                chunks.append(chunk)
                chunk_index += 1

                # Yield chunk
                yield chunk

                # Check for stop sequences
                if stop_sequences:
                    for seq in stop_sequences:
                        if seq in accumulated_text:
                            termination_reason = TerminationReason.EARLY_STOP
                            logger.info("Early stop triggered by sequence: %s", seq)
                            break

                    if termination_reason == TerminationReason.EARLY_STOP:
                        break

                # Quality check
                if quality_check and self.enable_quality_check:
                    should_stop, reason = self.quality_evaluator.should_terminate_early(
                        accumulated_text, chunk_index
                    )

                    if should_stop:
                        termination_reason = TerminationReason.QUALITY_THRESHOLD
                        logger.info("Early termination: %s", reason)
                        break

                # Timeout check
                if time.time() - start_time > self.timeout:
                    termination_reason = TerminationReason.TIMEOUT
                    logger.warning("Stream timeout after %ss", self.timeout)
                    break

        except asyncio.CancelledError:
            termination_reason = TerminationReason.USER_CANCELLED
            logger.info("Stream cancelled by user")

        except Exception as e:  # pylint: disable=broad-exception-caught
            termination_reason = TerminationReason.ERROR
            logger.error("Stream error: %s", e, exc_info=True)

        finally:
            # Store result
            duration = time.time() - start_time
            self._current_result = StreamResult(
                full_content=accumulated_text,
                chunks=chunks,
                termination_reason=termination_reason,
                total_tokens=chunk_index,
                duration=duration,
                metadata={"model": model, "tier": str(tier)},
            )

    def get_result(self) -> Optional[StreamResult]:
        """Get last stream result"""
        return self._current_result

    async def stream_with_callback(
        self,
        provider_router,
        tier,
        model: str,
        messages: List[Dict[str, str]],
        on_chunk: Callable[[StreamChunk], Any],
        on_complete: Optional[Callable[[StreamResult], Any]] = None,
        **kwargs,
    ):
        """
        Stream with callbacks.

        Args:
            provider_router: Provider router
            tier: LLM tier
            model: Model name
            messages: Messages
            on_chunk: Callback for each chunk (can be async)
            on_complete: Callback when stream completes (can be async)
            **kwargs: Additional stream arguments
        """
        async for chunk in self.stream(
            provider_router=provider_router,
            tier=tier,
            model=model,
            messages=messages,
            **kwargs,
        ):
            # Call chunk callback
            if asyncio.iscoroutinefunction(on_chunk):
                await on_chunk(chunk)
            else:
                on_chunk(chunk)

        # Call complete callback
        result = self.get_result()
        if on_complete and result is not None:
            if asyncio.iscoroutinefunction(on_complete):
                await on_complete(result)
            else:
                on_complete(result)

    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics"""
        if not self._current_result:
            return {"status": "no_streams"}

        result = self._current_result

        return {
            "total_tokens": result.total_tokens,
            "duration": result.duration,
            "tokens_per_second": result.total_tokens / result.duration
            if result.duration > 0
            else 0,
            "termination_reason": result.termination_reason.value,
            "content_length": len(result.full_content),
            "chunk_count": len(result.chunks),
        }


# Example usage
if __name__ == "__main__":

    async def main():
        # Setup
        router = build_local_router()

        # Create stream manager
        manager = StreamManager(enable_quality_check=True, timeout=30.0)

        print("Streaming LLM response:\n")

        # Stream with quality checking
        async for chunk in manager.stream(
            provider_router=router,
            tier=Tier.LOCAL_FREE,
            model="llama3.1:8b",
            messages=[{"role": "user", "content": "Write a short poem about AI."}],
            quality_check=True,
            max_tokens=200,
        ):
            print(chunk.content, end="", flush=True)

        print("\n")

        # Get result
        result = manager.get_result()
        print(f"\nTermination reason: {result.termination_reason.value}")
        print(f"Stats: {manager.get_stats()}")

    asyncio.run(main())
