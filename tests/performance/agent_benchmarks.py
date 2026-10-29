"""
Multi-Agent System Performance Benchmarks - TASK-042

Specific benchmarks for multi-agent workflows:
- Agent coordination overhead
- Tool execution performance
- Streaming latency
- Workflow versioning overhead
- A/B testing performance
- RAG search performance
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from tests.performance.benchmark import PerformanceBenchmark  # noqa: E402
from src.tools.registry import ToolRegistry  # noqa: E402
from src.agents.coordinator import AgentCoordinator, EventBus  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402


class AgentBenchmarks:
    """
    Multi-agent system benchmarks.

    Benchmarks:
    1. Tool registry lookup and execution
    2. Agent message passing
    3. Workflow coordination
    4. Streaming performance
    5. Metadata filtering
    """

    def __init__(self):
        self.benchmark = PerformanceBenchmark()

    async def run_all(self):
        """Run all agent benchmarks"""
        print("\n" + "=" * 70)
        print("  🤖 MULTI-AGENT SYSTEM PERFORMANCE BENCHMARKS")
        print("=" * 70)

        await self.benchmark_tool_registry()
        await self.benchmark_agent_messaging()
        await self.benchmark_tool_execution()
        await self.benchmark_concurrent_agents()

        # Print final comparison
        self.benchmark.print_comparison(self.benchmark.results)

        # Export results
        self.benchmark.export_json("agent_benchmark_results.json")

    async def benchmark_tool_registry(self):
        """Benchmark tool registry operations"""
        print("\n📦 Tool Registry Benchmark")

        registry = ToolRegistry()

        # Register 100 tools
        for i in range(100):

            @registry.register_function(description=f"Tool {i}", category="test")
            def tool_func(x: int = i):
                return x * 2

        # Benchmark: Tool lookup
        async def lookup_tool():
            schema = registry.get_tool_schema("tool_func")
            return schema

        result1 = await self.benchmark.run(
            name="Tool Registry Lookup",
            func=lookup_tool,
            iterations=10000,
            concurrency=50,
        )

        # Benchmark: Tool execution
        async def execute_tool():
            result = await registry.execute("tool_func", {"x": 10})
            return result

        result2 = await self.benchmark.run(
            name="Tool Execution", func=execute_tool, iterations=1000, concurrency=20
        )

        self.benchmark.print_report(result1)
        self.benchmark.print_report(result2)

    async def benchmark_agent_messaging(self):
        """Benchmark agent message passing"""
        print("\n💬 Agent Messaging Benchmark")

        event_bus = EventBus()

        # Create mock agents
        messages_received = []

        async def message_callback(message):
            messages_received.append(message)

        await event_bus.subscribe("agent1", message_callback)
        await event_bus.subscribe("agent2", message_callback)

        # Benchmark: Message publish
        from src.agents.coordinator import Message, MessageType

        async def publish_message():
            message = Message(
                message_id=f"msg_{len(messages_received)}",
                type=MessageType.TASK_ASSIGNMENT,
                sender="coordinator",
                recipient="agent1",
                content={"task": "test"},
            )
            await event_bus.publish(message)

        result = await self.benchmark.run(
            name="Message Publishing",
            func=publish_message,
            iterations=1000,
            concurrency=10,
        )

        self.benchmark.print_report(result)

    async def benchmark_tool_execution(self):
        """Benchmark different tool types"""
        print("\n🔧 Tool Execution Types Benchmark")

        registry = ToolRegistry()

        # Fast tool (simple math)
        @registry.register_function(description="Fast math", category="math")
        def fast_tool(a: int, b: int):
            return a + b

        # Medium tool (iteration)
        @registry.register_function(description="Medium iteration", category="compute")
        def medium_tool(n: int):
            return sum(range(n))

        # Slow tool (with sleep)
        @registry.register_function(description="Slow I/O", category="io")
        async def slow_tool(delay: float):
            await asyncio.sleep(delay)
            return "done"

        # Benchmark fast tool
        async def execute_fast():
            return await registry.execute("fast_tool", {"a": 5, "b": 10})

        result1 = await self.benchmark.run(
            name="Fast Tool (Math)",
            func=execute_fast,
            iterations=10000,
            concurrency=100,
        )

        # Benchmark medium tool
        async def execute_medium():
            return await registry.execute("medium_tool", {"n": 1000})

        result2 = await self.benchmark.run(
            name="Medium Tool (Compute)",
            func=execute_medium,
            iterations=1000,
            concurrency=50,
        )

        # Benchmark slow tool
        async def execute_slow():
            return await registry.execute("slow_tool", {"delay": 0.01})

        result3 = await self.benchmark.run(
            name="Slow Tool (I/O)", func=execute_slow, iterations=100, concurrency=10
        )

        self.benchmark.print_report(result1)
        self.benchmark.print_report(result2)
        self.benchmark.print_report(result3)

    async def benchmark_concurrent_agents(self):
        """Benchmark concurrent agent execution"""
        print("\n🚀 Concurrent Agent Execution Benchmark")

        event_bus = EventBus()
        coordinator = AgentCoordinator(event_bus)

        # Create mock agents
        mock_router = AsyncMock()
        mock_router.chat_completion = AsyncMock(
            return_value=AsyncMock(content='{"result": "success"}')
        )

        registry = ToolRegistry()

        from src.agents.coder import CoderAgent

        # Create multiple agents
        agents = []
        for i in range(10):
            agent = CoderAgent(
                agent_id=f"coder_{i}",
                event_bus=event_bus,
                tool_registry=registry,
                provider_router=mock_router,
            )
            agents.append(agent)
            await coordinator.register_agent(agent)

        # Benchmark: Concurrent task assignment
        async def assign_task():
            task = {"instruction": "Test task"}
            agent_id = f"coder_{len(agents) % 10}"
            await coordinator.assign_task(agent_id, task)

        result = await self.benchmark.run(
            name="Concurrent Task Assignment (10 agents)",
            func=assign_task,
            iterations=100,
            concurrency=20,
        )

        self.benchmark.print_report(result)


class RAGBenchmarks:
    """RAG system benchmarks"""

    def __init__(self):
        self.benchmark = PerformanceBenchmark()

    async def run_all(self):
        """Run all RAG benchmarks"""
        print("\n" + "=" * 70)
        print("  🔍 RAG SYSTEM PERFORMANCE BENCHMARKS")
        print("=" * 70)

        await self.benchmark_bm25_search()
        await self.benchmark_metadata_filtering()

        # Print comparison
        self.benchmark.print_comparison(self.benchmark.results)

        # Export results
        self.benchmark.export_json("rag_benchmark_results.json")

    async def benchmark_bm25_search(self):
        """Benchmark BM25 search"""
        print("\n📚 BM25 Search Benchmark")

        from src.rag.bm25_index import BM25Index

        # Create index with 1000 documents
        bm25 = BM25Index()
        documents = [f"This is document {i} about topic {i % 10}" for i in range(1000)]
        doc_ids = [f"doc_{i}" for i in range(1000)]

        bm25.index_documents(documents, doc_ids)

        # Benchmark: Search
        async def search_bm25():
            results = bm25.search("document topic", top_k=10)
            return results

        result = await self.benchmark.run(
            name="BM25 Search (1000 docs)",
            func=search_bm25,
            iterations=1000,
            concurrency=20,
        )

        self.benchmark.print_report(result)

    async def benchmark_metadata_filtering(self):
        """Benchmark metadata filter construction"""
        print("\n🔎 Metadata Filtering Benchmark")

        from src.rag.metadata_filter import (
            FilterBuilder,
            CategoryFilter,
        )

        # Benchmark: Simple filter construction
        async def build_simple_filter():
            filter = CategoryFilter.by_category("tech")
            return filter

        result1 = await self.benchmark.run(
            name="Simple Filter Construction",
            func=build_simple_filter,
            iterations=10000,
            concurrency=50,
        )

        # Benchmark: Complex filter construction
        async def build_complex_filter():
            filter = (
                FilterBuilder()
                .add_category("tech")
                .add_last_n_days("created_at", 7)
                .add_score_above("relevance", 0.8)
                .add_tags(["python", "ai"], match_all=True)
                .build()
            )
            return filter

        result2 = await self.benchmark.run(
            name="Complex Filter Construction",
            func=build_complex_filter,
            iterations=10000,
            concurrency=50,
        )

        self.benchmark.print_report(result1)
        self.benchmark.print_report(result2)


async def main():
    """Run all benchmarks"""
    # Agent benchmarks
    agent_bench = AgentBenchmarks()
    await agent_bench.run_all()

    # RAG benchmarks
    rag_bench = RAGBenchmarks()
    await rag_bench.run_all()

    print("\n" + "=" * 70)
    print("  ✅ ALL BENCHMARKS COMPLETE")
    print("=" * 70)
    print("\n  Results exported to:")
    print("    - agent_benchmark_results.json")
    print("    - rag_benchmark_results.json")
    print()


if __name__ == "__main__":
    asyncio.run(main())
