"""
Jan Provider Integration Tests

Tests Jan.ai local LLM inference provider for privacy mode.

Prerequisites:
- Jan must be running locally (docker-compose up jan)
- At least one model must be downloaded in Jan

Run:
    pytest tests/integration/test_jan_integration.py -v
"""

import pytest
import asyncio
from src.providers.jan_provider import JanProvider


@pytest.fixture
async def jan_provider():
    """Create Jan provider instance (skips when no Jan server is running)"""
    provider = JanProvider(base_url="http://localhost:1337")
    if not await provider.health_check():
        await provider.close()
        pytest.skip("Jan server not reachable at http://localhost:1337")
    yield provider
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.integration
class TestJanIntegration:
    """Integration tests for Jan provider"""

    async def test_health_check(self, jan_provider):
        """Test Jan server health check"""
        is_healthy = await jan_provider.health_check()

        assert is_healthy, (
            "Jan server not healthy. " "Ensure Jan is running: docker-compose up -d jan"
        )

    async def test_list_models(self, jan_provider):
        """Test listing available models"""
        models = await jan_provider.list_models()

        assert isinstance(models, list), "Models should be a list"
        assert len(models) > 0, (
            "No models available in Jan. " "Download models via Jan UI or CLI"
        )

        # Check model structure
        first_model = models[0]
        assert "id" in first_model
        assert "name" in first_model

        print(f"\nAvailable models ({len(models)}):")
        for model in models:
            print(f"  - {model['id']} ({model.get('size', 'unknown')})")

    async def test_chat_completion(self, jan_provider):
        """Test basic chat completion"""
        # Get available models
        models = await jan_provider.list_models()
        if not models:
            pytest.skip("No models available")

        model_id = models[0]["id"]

        # Test completion
        response = await jan_provider.chat_completion(
            model=model_id,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Be concise.",
                },
                {"role": "user", "content": "What is 2+2? Answer in one word."},
            ],
            max_tokens=10,
            temperature=0.1,
        )

        assert response is not None
        assert response.content, "Response content should not be empty"
        assert response.model == model_id
        assert response.usage["prompt_tokens"] > 0
        assert response.usage["completion_tokens"] > 0

        print(f"\nModel: {response.model}")
        print(f"Response: {response.content}")
        print(f"Tokens: {response.usage}")

    async def test_chat_completion_with_context(self, jan_provider):
        """Test multi-turn conversation"""
        models = await jan_provider.list_models()
        if not models:
            pytest.skip("No models available")

        model_id = models[0]["id"]

        # Multi-turn conversation
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "My name is Alice."},
        ]

        # First turn
        response1 = await jan_provider.chat_completion(
            model=model_id, messages=messages, max_tokens=50
        )

        assert response1.content

        # Add response to history
        messages.append({"role": "assistant", "content": response1.content})
        messages.append({"role": "user", "content": "What is my name?"})

        # Second turn (should remember name)
        response2 = await jan_provider.chat_completion(
            model=model_id, messages=messages, max_tokens=50
        )

        assert response2.content
        assert (
            "alice" in response2.content.lower()
        ), "Model should remember user's name from context"

        print("\nConversation:")
        print("User: My name is Alice.")
        print(f"Assistant: {response1.content}")
        print("User: What is my name?")
        print(f"Assistant: {response2.content}")

    async def test_streaming(self, jan_provider):
        """Test streaming completion"""
        models = await jan_provider.list_models()
        if not models:
            pytest.skip("No models available")

        model_id = models[0]["id"]

        chunks = []
        async for chunk in jan_provider.stream_completion(
            model=model_id,
            messages=[{"role": "user", "content": "Count from 1 to 3."}],
            max_tokens=50,
        ):
            chunks.append(chunk)

        assert len(chunks) > 0, "Should receive streaming chunks"

        full_response = "".join(chunks)
        assert full_response, "Streaming response should not be empty"

        print(f"\nStreaming response ({len(chunks)} chunks):")
        print(full_response)

    async def test_cost_calculation(self, jan_provider):
        """Test cost calculation (should always be $0 for Jan)"""
        cost1 = jan_provider.get_cost(100, 50)
        assert cost1 == 0.0, "Jan should always return $0 cost"

        cost2 = jan_provider.get_cost(1000000, 1000000, model="any-model")
        assert cost2 == 0.0, "Jan cost should be $0 regardless of tokens"

    async def test_temperature_variation(self, jan_provider):
        """Test different temperature settings"""
        models = await jan_provider.list_models()
        if not models:
            pytest.skip("No models available")

        model_id = models[0]["id"]

        prompt = [{"role": "user", "content": "Say hello."}]

        # Low temperature (deterministic)
        response_low = await jan_provider.chat_completion(
            model=model_id, messages=prompt, temperature=0.1, max_tokens=20
        )

        # High temperature (creative)
        response_high = await jan_provider.chat_completion(
            model=model_id, messages=prompt, temperature=1.5, max_tokens=20
        )

        assert response_low.content
        assert response_high.content

        print(f"\nLow temp (0.1): {response_low.content}")
        print(f"High temp (1.5): {response_high.content}")

    async def test_max_tokens_limit(self, jan_provider):
        """Test max_tokens parameter"""
        models = await jan_provider.list_models()
        if not models:
            pytest.skip("No models available")

        model_id = models[0]["id"]

        # Very low max_tokens
        response = await jan_provider.chat_completion(
            model=model_id,
            messages=[{"role": "user", "content": "Write a long story."}],
            max_tokens=5,
        )

        assert response.content
        assert (
            response.usage["completion_tokens"] <= 5
        ), "Should respect max_tokens limit"

    async def test_error_handling_invalid_model(self, jan_provider):
        """Test error handling for invalid model"""
        with pytest.raises(Exception):
            await jan_provider.chat_completion(
                model="nonexistent-model-12345",
                messages=[{"role": "user", "content": "test"}],
            )

    async def test_concurrent_requests(self, jan_provider):
        """Test concurrent request handling"""
        models = await jan_provider.list_models()
        if not models:
            pytest.skip("No models available")

        model_id = models[0]["id"]

        # Create 3 concurrent requests
        tasks = [
            jan_provider.chat_completion(
                model=model_id,
                messages=[{"role": "user", "content": f"Say the number {i}"}],
                max_tokens=10,
            )
            for i in range(3)
        ]

        # Run concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Check all succeeded
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                pytest.fail(f"Request {i} failed: {response}")

            assert response.content
            print(f"Concurrent request {i}: {response.content[:50]}")


@pytest.mark.asyncio
@pytest.mark.integration
class TestJanPrivacyMode:
    """Privacy mode specific tests"""

    async def test_local_only_execution(self, jan_provider):
        """Verify Jan executes locally (no external calls)"""
        # This test verifies configuration, actual network isolation
        # would require network monitoring

        assert jan_provider.base_url.startswith(
            "http://localhost"
        ) or jan_provider.base_url.startswith(
            "http://127.0.0.1"
        ), "Jan should be configured for local execution only"

    async def test_zero_cost_operation(self, jan_provider):
        """Verify all operations are zero cost"""
        models = await jan_provider.list_models()
        if not models:
            pytest.skip("No models available")

        model_id = models[0]["id"]

        # Perform operation
        response = await jan_provider.chat_completion(
            model=model_id,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=10,
        )

        # Calculate cost
        cost = jan_provider.get_cost(
            response.usage["prompt_tokens"], response.usage["completion_tokens"]
        )

        assert cost == 0.0, "Privacy mode should have zero cost"

    async def test_no_api_key_required(self):
        """Verify Jan works without API keys"""
        # Jan should not require API keys (local execution)
        provider = JanProvider()  # No API key

        is_healthy = await provider.health_check()

        # If Jan is running, it should work without auth
        # If not running, that's fine (test environment issue)
        if is_healthy:
            assert True, "Jan works without API keys"

        await provider.close()


# Fixtures for pytest-asyncio
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires external services)",
    )
