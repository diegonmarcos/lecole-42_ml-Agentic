"""Interactive smoke demo shared by the provider modules' ``__main__`` blocks."""

from typing import Optional

from .base import LLMProvider


async def run_provider_demo(
    provider: LLMProvider,
    name: str,
    chat_model: str,
    stream_model: Optional[str] = None,
) -> None:
    """Run a health check, one chat completion and one streamed completion."""
    is_healthy = await provider.health_check()
    print(f"{name} health: {is_healthy}")

    response = await provider.chat_completion(
        model=chat_model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"},
        ],
        temperature=0.7,
        max_tokens=100,
    )

    print(f"Response: {response.content}")
    print(f"Usage: {response.usage}")

    cost = provider.get_cost(
        response.usage["prompt_tokens"], response.usage["completion_tokens"]
    )
    print(f"Cost: ${cost:.6f}")

    print("\nStreaming:")
    async for chunk in provider.stream_completion(
        model=stream_model or chat_model,
        messages=[{"role": "user", "content": "Count from 1 to 5."}],
        max_tokens=50,
    ):
        print(chunk, end="", flush=True)
    print()

    close = getattr(provider, "close", None)
    if close is not None:
        await close()
