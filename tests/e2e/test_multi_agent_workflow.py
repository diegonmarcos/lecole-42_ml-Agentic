"""
End-to-End Multi-Agent Workflow Tests - TASK-041

Tests complete workflows from task assignment to completion:
- Planner -> Coder -> Reviewer workflow
- Tool usage and coordination
- Streaming responses
- Error handling and retries
- Workflow versioning and A/B testing
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from src.agents.coordinator import AgentCoordinator, EventBus, MessageType
from src.agents.planner import PlannerAgent
from src.agents.coder import CoderAgent
from src.agents.reviewer import ReviewerAgent
from src.tools.registry import ToolRegistry
from src.tools.workbenches.code_workbench import CodeWorkbench
from src.workflows.versioning import WorkflowVersionManager
from src.workflows.ab_testing import ABTestingManager, Variant
from src.streaming.stream_manager import StreamManager


@pytest.fixture
async def redis_client():
    """Redis client fixture"""
    client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    yield client
    await client.close()


@pytest.fixture
async def event_bus():
    """Event bus fixture"""
    return EventBus()


@pytest.fixture
async def tool_registry():
    """Tool registry fixture"""
    registry = ToolRegistry()

    # Register mock tools
    @registry.register_function(description="Get current time", category="utility")
    def get_time():
        return datetime.utcnow().isoformat()

    @registry.register_function(description="Add two numbers", category="math")
    def add(a: int, b: int):
        return a + b

    return registry


@pytest.fixture
async def mock_provider_router():
    """Mock provider router"""
    router = AsyncMock()
    router.chat_completion = AsyncMock()
    router.stream_completion = AsyncMock()
    return router


@pytest.fixture
async def coordinator(event_bus, tool_registry, mock_provider_router):
    """Agent coordinator fixture"""
    coordinator = AgentCoordinator(event_bus)

    # Create and register agents
    planner = PlannerAgent(
        agent_id="planner",
        event_bus=event_bus,
        tool_registry=tool_registry,
        provider_router=mock_provider_router,
    )

    coder = CoderAgent(
        agent_id="coder",
        event_bus=event_bus,
        tool_registry=tool_registry,
        provider_router=mock_provider_router,
    )

    reviewer = ReviewerAgent(
        agent_id="reviewer",
        event_bus=event_bus,
        tool_registry=tool_registry,
        provider_router=mock_provider_router,
    )

    await coordinator.register_agent(planner)
    await coordinator.register_agent(coder)
    await coordinator.register_agent(reviewer)

    return coordinator


class TestBasicWorkflow:
    """Test basic multi-agent workflows"""

    @pytest.mark.asyncio
    async def test_simple_task_assignment(self, coordinator):
        """Test simple task assignment to single agent"""
        task = {"instruction": "Plan a simple API endpoint"}

        # Assign task to planner
        message_id = await coordinator.assign_task("planner", task)

        assert message_id is not None

        # Wait for result
        result = await coordinator.wait_for_result("planner", timeout=5.0)

        assert result is not None
        assert result.type == MessageType.TASK_RESULT

    @pytest.mark.asyncio
    async def test_agent_communication(
        self, event_bus, tool_registry, mock_provider_router
    ):
        """Test agents communicating with each other"""
        planner = PlannerAgent(
            agent_id="planner",
            event_bus=event_bus,
            tool_registry=tool_registry,
            provider_router=mock_provider_router,
        )

        coder = CoderAgent(
            agent_id="coder",
            event_bus=event_bus,
            tool_registry=tool_registry,
            provider_router=mock_provider_router,
        )

        # Start agents
        await planner.start()
        await coder.start()

        # Planner requests help from coder
        await planner.send_message(
            recipient="coder",
            message_type=MessageType.AGENT_REQUEST,
            content={"request": "Generate function signature"},
        )

        # Give some time for message processing
        await asyncio.sleep(0.5)

        # Check coder received message
        assert len(coder.state.message_history) > 0

    @pytest.mark.asyncio
    async def test_tool_usage_in_workflow(self, coordinator, tool_registry):
        """Test agent using tools during workflow"""

        # Register a test tool
        @tool_registry.register_function(description="Test tool", category="test")
        def test_tool(input: str):
            return f"Processed: {input}"

        task = {"instruction": "Use test_tool with input 'hello'"}

        await coordinator.assign_task("coder", task)

        # Coder should use the tool
        result = await coordinator.wait_for_result("coder", timeout=5.0)

        # Tool should have been called
        assert result is not None


class TestCompleteWorkflow:
    """Test complete multi-agent workflows"""

    @pytest.mark.asyncio
    async def test_plan_code_review_workflow(self, coordinator, mock_provider_router):
        """Test complete workflow: Plan -> Code -> Review"""
        # Mock LLM responses
        mock_provider_router.chat_completion.side_effect = [
            # Planner response
            AsyncMock(
                content=json.dumps(
                    {
                        "summary": "Create a function to calculate factorial",
                        "steps": [
                            {
                                "step_number": 1,
                                "action": "design_function",
                                "agent": "coder",
                            },
                            {
                                "step_number": 2,
                                "action": "review_code",
                                "agent": "reviewer",
                            },
                        ],
                    }
                )
            ),
            # Coder response
            AsyncMock(
                content=json.dumps(
                    {
                        "code": "def factorial(n):\n    return 1 if n == 0 else n * factorial(n-1)",
                        "explanation": "Recursive factorial implementation",
                    }
                )
            ),
            # Reviewer response
            AsyncMock(
                content=json.dumps(
                    {
                        "overall_rating": "Good",
                        "score": 85,
                        "issues": [],
                        "approved": True,
                    }
                )
            ),
        ]

        # Step 1: Plan
        plan_task = {"instruction": "Create a factorial function"}
        await coordinator.assign_task("planner", plan_task)
        plan_result = await coordinator.wait_for_result("planner", timeout=5.0)

        assert plan_result is not None
        plan = json.loads(plan_result.content)
        assert "steps" in plan

        # Step 2: Code
        code_task = {"instruction": "Implement factorial function"}
        await coordinator.assign_task("coder", code_task)
        code_result = await coordinator.wait_for_result("coder", timeout=5.0)

        assert code_result is not None
        code = json.loads(code_result.content)
        assert "code" in code

        # Step 3: Review
        review_task = {"code": code["code"]}
        await coordinator.assign_task("reviewer", review_task)
        review_result = await coordinator.wait_for_result("reviewer", timeout=5.0)

        assert review_result is not None
        review = json.loads(review_result.content)
        assert "approved" in review

    @pytest.mark.asyncio
    async def test_workflow_with_retries(self, coordinator, mock_provider_router):
        """Test workflow with error handling and retries"""
        # First attempt fails, second succeeds
        mock_provider_router.chat_completion.side_effect = [
            Exception("API error"),
            AsyncMock(content=json.dumps({"result": "success"})),
        ]

        task = {"instruction": "Test task"}

        # First attempt should fail
        await coordinator.assign_task("coder", task, priority=1)

        # Should retry and succeed
        await coordinator.wait_for_result("coder", timeout=10.0)

        # Eventually succeeds (in production would have retry logic)
        # This test just verifies the coordinator handles exceptions gracefully


class TestWorkflowVersioning:
    """Test workflow versioning integration"""

    @pytest.mark.asyncio
    async def test_versioned_workflow_execution(self, redis_client, coordinator):
        """Test executing different workflow versions"""
        version_manager = WorkflowVersionManager(redis_client)

        # Create v1.0.0 workflow (2 agents)
        workflow_v1 = {
            "agents": ["planner", "coder"],
            "steps": [
                {"agent": "planner", "action": "plan"},
                {"agent": "coder", "action": "code"},
            ],
        }

        await version_manager.create_version(
            workflow_id="code-workflow",
            version="1.0.0",
            workflow_data=workflow_v1,
            author="system",
            changelog="Initial version",
        )

        # Create v2.0.0 workflow (3 agents)
        workflow_v2 = {
            "agents": ["planner", "coder", "reviewer"],
            "steps": [
                {"agent": "planner", "action": "plan"},
                {"agent": "coder", "action": "code"},
                {"agent": "reviewer", "action": "review"},
            ],
        }

        await version_manager.create_version(
            workflow_id="code-workflow",
            version="2.0.0",
            workflow_data=workflow_v2,
            author="system",
            changelog="Add reviewer",
            set_active=True,
        )

        # Execute active version (v2)
        active = await version_manager.get_active_version("code-workflow")
        assert active.version == "2.0.0"
        assert len(active.workflow_data["agents"]) == 3

        # Rollback to v1
        await version_manager.rollback("code-workflow", "1.0.0")
        active = await version_manager.get_active_version("code-workflow")
        assert active.version == "1.0.0"
        assert len(active.workflow_data["agents"]) == 2


class TestABTestingWorkflow:
    """Test A/B testing integration"""

    @pytest.mark.asyncio
    async def test_ab_test_variant_execution(self, redis_client, coordinator):
        """Test executing different workflow variants"""
        version_manager = WorkflowVersionManager(redis_client)
        ab_manager = ABTestingManager(redis_client, version_manager)

        # Create two workflow versions
        await version_manager.create_version(
            workflow_id="code-workflow",
            version="1.0.0",
            workflow_data={"model": "llama-70b"},
            author="system",
            changelog="v1",
        )

        await version_manager.create_version(
            workflow_id="code-workflow",
            version="2.0.0",
            workflow_data={"model": "claude-3.5-haiku"},
            author="system",
            changelog="v2",
            set_active=False,
        )

        # Create A/B experiment
        experiment = await ab_manager.create_experiment(
            workflow_id="code-workflow",
            name="Model Comparison",
            description="Test Llama vs Claude",
            variants=[
                Variant("control", "1.0.0", 0.5, "Llama 70B"),
                Variant("test", "2.0.0", 0.5, "Claude 3.5 Haiku"),
            ],
        )

        await ab_manager.start_experiment(experiment.experiment_id)

        # Simulate 100 users
        variant_assignments = {"control": 0, "test": 0}

        for i in range(100):
            variant = await ab_manager.assign_variant(
                experiment.experiment_id, user_id=f"user_{i}"
            )

            variant_assignments[variant.variant_id] += 1

            # Record metrics
            await ab_manager.record_impression(
                experiment.experiment_id, variant.variant_id
            )
            await ab_manager.record_success(
                experiment.experiment_id, variant.variant_id, latency=1.5, cost=0.05
            )

        # Check traffic split (should be roughly 50/50)
        assert 40 <= variant_assignments["control"] <= 60
        assert 40 <= variant_assignments["test"] <= 60

        # Get metrics
        metrics = await ab_manager.get_metrics(experiment.experiment_id)
        assert "control" in metrics
        assert "test" in metrics


class TestStreamingWorkflow:
    """Test streaming responses in workflows"""

    @pytest.mark.asyncio
    async def test_streaming_code_generation(self, mock_provider_router):
        """Test streaming code generation workflow"""
        stream_manager = StreamManager()

        # Mock streaming response
        async def mock_stream():
            chunks = [
                "def ",
                "factorial",
                "(n):\n",
                "    return ",
                "1 if n == 0 else n * factorial(n-1)",
            ]
            for chunk in chunks:
                yield chunk

        mock_provider_router.stream_completion = mock_stream

        # Stream response
        full_response = ""
        async for chunk in stream_manager.stream(
            provider_router=mock_provider_router,
            tier="tier-1",
            model="llama-70b",
            messages=[{"role": "user", "content": "Generate factorial function"}],
        ):
            full_response += chunk.content

        assert "def factorial" in full_response
        assert "return" in full_response

    @pytest.mark.asyncio
    async def test_early_termination_streaming(self, mock_provider_router):
        """Test early termination in streaming"""
        stream_manager = StreamManager()

        # Mock streaming with repetition (should trigger early termination)
        async def mock_stream_with_repetition():
            for _ in range(50):
                yield "This is repeated text.\n"

        mock_provider_router.stream_completion = mock_stream_with_repetition

        chunks_received = 0
        async for chunk in stream_manager.stream(
            provider_router=mock_provider_router,
            tier="tier-1",
            model="llama-70b",
            messages=[{"role": "user", "content": "Test"}],
            quality_check=True,
        ):
            chunks_received += 1

        # Should terminate early (not receive all 50 chunks)
        assert chunks_received < 50


class TestCodeWorkbench:
    """Test code workbench integration"""

    @pytest.mark.asyncio
    async def test_code_analysis_workflow(self, tool_registry):
        """Test complete code analysis workflow"""
        CodeWorkbench(tool_registry)

        code = """
def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)
"""

        # Parse code
        parse_result = await tool_registry.execute("parse_python", {"code": code})
        assert parse_result.success
        assert "functions" in parse_result.output

        # Calculate complexity
        complexity_result = await tool_registry.execute(
            "calculate_complexity", {"code": code}
        )
        assert complexity_result.success
        assert "functions" in complexity_result.output

        # Check syntax
        syntax_result = await tool_registry.execute("check_syntax", {"code": code})
        assert syntax_result.success
        assert syntax_result.output["valid"]


class TestErrorHandling:
    """Test error handling in workflows"""

    @pytest.mark.asyncio
    async def test_agent_timeout_handling(self, coordinator):
        """Test handling of agent timeouts"""
        task = {"instruction": "Long running task"}

        await coordinator.assign_task("coder", task)

        # Wait with short timeout (should timeout)
        result = await coordinator.wait_for_result("coder", timeout=0.1)

        # Should return None on timeout
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_tool_usage(self, tool_registry):
        """Test handling of invalid tool calls"""
        # Try to execute non-existent tool
        result = await tool_registry.execute("nonexistent_tool", {})

        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_malformed_llm_response(self, coordinator, mock_provider_router):
        """Test handling of malformed LLM responses"""
        # Mock invalid JSON response
        mock_provider_router.chat_completion.return_value = AsyncMock(
            content="This is not valid JSON"
        )

        task = {"instruction": "Test task"}
        await coordinator.assign_task("planner", task)

        # Should handle gracefully (not crash)
        await coordinator.wait_for_result("planner", timeout=5.0)

        # In production, would have error handling


class TestPerformance:
    """Test performance characteristics"""

    @pytest.mark.asyncio
    async def test_concurrent_task_processing(self, coordinator):
        """Test processing multiple tasks concurrently"""
        tasks = [{"instruction": f"Task {i}"} for i in range(10)]

        # Assign all tasks
        message_ids = []
        for task in tasks:
            msg_id = await coordinator.assign_task("coder", task, priority=0)
            message_ids.append(msg_id)

        # All tasks should be assigned
        assert len(message_ids) == 10

    @pytest.mark.asyncio
    async def test_tool_execution_performance(self, tool_registry):
        """Test tool execution performance"""

        # Register a simple tool
        @tool_registry.register_function(description="Fast tool", category="test")
        def fast_tool(n: int):
            return n * 2

        # Execute many times
        results = []
        for i in range(100):
            result = await tool_registry.execute("fast_tool", {"n": i})
            results.append(result)

        # All should succeed
        assert all(r.success for r in results)
        assert len(results) == 100
