"""
Base Agent Class - Foundation for all specialized agents

Provides common agent functionality:
- Message handling
- Tool access
- LLM integration
- State management
- Memory
"""

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.providers.router import ProviderRouter, Tier, build_local_router
from src.tools.registry import ToolRegistry, get_registry

from .coordinator import AgentCoordinator, Message, MessageType

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Agent state"""

    agent_id: str
    status: str  # idle, thinking, executing, waiting
    current_task: Optional[Dict[str, Any]] = None
    memory: List[Dict[str, Any]] = field(default_factory=list)
    tool_usage_count: Dict[str, int] = field(default_factory=dict)
    message_history: List[Message] = field(default_factory=list)


class BaseAgent(ABC):
    """
    Base class for all agents.

    Subclasses must implement:
    - process_task(): Main task processing logic
    - get_system_prompt(): Agent-specific system prompt
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: List[str],
        coordinator: AgentCoordinator,
        provider_router: ProviderRouter,
        tool_registry: Optional[ToolRegistry] = None,
        tier: Tier = Tier.CLOUD_CHEAP,
        model: Optional[str] = None,
    ):
        """
        Initialize base agent.

        Args:
            agent_id: Unique agent ID
            agent_type: Agent type (planner, coder, reviewer, etc.)
            capabilities: List of capabilities
            coordinator: Agent coordinator
            provider_router: LLM provider router
            tool_registry: Tool registry
            tier: Default LLM tier
            model: Default LLM model
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.coordinator = coordinator
        self.provider_router = provider_router
        self.tool_registry = tool_registry or get_registry()
        self.tier = tier
        self.model = model

        self.state = AgentState(agent_id=agent_id, status="idle")
        self._running = False

    async def start(self):
        """Start agent"""
        # Register with coordinator
        await self.coordinator.register_agent(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            capabilities=self.capabilities,
            callback=self._handle_message,
        )

        self._running = True
        logger.info("Agent %s started", self.agent_id)

    async def stop(self):
        """Stop agent"""
        self._running = False

        # Unregister from coordinator
        await self.coordinator.unregister_agent(self.agent_id)

        logger.info("Agent %s stopped", self.agent_id)

    async def _handle_message(self, message: Message):
        """
        Handle incoming message.

        Args:
            message: Message from event bus
        """
        self.state.message_history.append(message)

        if message.type == MessageType.TASK_ASSIGNMENT:
            await self._handle_task_assignment(message)

        elif message.type == MessageType.AGENT_REQUEST:
            await self._handle_agent_request(message)

        elif message.type == MessageType.SYSTEM_EVENT:
            await self._handle_system_event(message)

    async def _handle_task_assignment(self, message: Message):
        """Handle task assignment"""
        self.state.status = "thinking"
        self.state.current_task = message.content

        logger.info("Agent %s processing task: %s", self.agent_id, message.message_id)

        try:
            # Process task (implemented by subclass)
            result = await self.process_task(message.content)

            # Send result
            await self._send_result(message.message_id, result)

            self.state.status = "idle"
            self.state.current_task = None

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Task processing error: %s", e, exc_info=True)

            # Send error
            await self._send_error(message.message_id, str(e))

            self.state.status = "idle"

    async def _handle_agent_request(self, message: Message):
        """Handle request from another agent"""
        # Subclasses can override

    async def _handle_system_event(self, message: Message):
        """Handle system event"""
        # Subclasses can override

    async def _send_result(self, parent_message_id: str, result: Any):
        """Send task result"""

        result_message = Message(
            message_id=str(uuid.uuid4()),
            type=MessageType.TASK_RESULT,
            sender=self.agent_id,
            recipient="coordinator",
            content=result,
            parent_id=parent_message_id,
        )

        await self.coordinator.event_bus.publish(result_message)

    async def _send_error(self, parent_message_id: str, error: str):
        """Send error message"""

        error_message = Message(
            message_id=str(uuid.uuid4()),
            type=MessageType.ERROR,
            sender=self.agent_id,
            recipient="coordinator",
            content={"error": error},
            parent_id=parent_message_id,
        )

        await self.coordinator.event_bus.publish(error_message)

    async def call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tier: Optional[Tier] = None,
    ) -> str:
        """
        Call LLM with agent's system prompt.

        Args:
            messages: Message history
            temperature: Sampling temperature
            max_tokens: Max tokens
            tier: Override default tier

        Returns:
            LLM response content
        """
        # Prepend system prompt
        system_prompt = self.get_system_prompt()

        full_messages = [{"role": "system", "content": system_prompt}, *messages]

        # Call LLM
        response = await self.provider_router.chat_completion(
            tier=tier or self.tier,
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.content

    async def use_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """
        Use a tool from registry.

        Args:
            tool_name: Tool name
            parameters: Tool parameters

        Returns:
            Tool result
        """
        self.state.status = "executing"

        try:
            result = await self.tool_registry.execute(
                name=tool_name, parameters=parameters
            )

            # Update stats
            self.state.tool_usage_count[tool_name] = (
                self.state.tool_usage_count.get(tool_name, 0) + 1
            )

            return result.output if result.success else None

        finally:
            self.state.status = "thinking"

    def remember(self, key: str, value: Any):
        """
        Store information in agent memory.

        Args:
            key: Memory key
            value: Value to store
        """
        self.state.memory.append({"key": key, "value": value, "timestamp": time.time()})

    def recall(self, key: str, default: Any = None) -> Any:
        """
        Recall information from memory.

        Args:
            key: Memory key
            default: Default value if not found

        Returns:
            Stored value or default
        """
        for item in reversed(self.state.memory):
            if item["key"] == key:
                return item["value"]

        return default

    @abstractmethod
    async def process_task(self, task: Dict[str, Any]) -> Any:
        """
        Process assigned task (must be implemented by subclass).

        Args:
            task: Task data

        Returns:
            Task result
        """

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get agent-specific system prompt (must be implemented by subclass).

        Returns:
            System prompt
        """

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "status": self.state.status,
            "total_messages": len(self.state.message_history),
            "tool_usage": dict(self.state.tool_usage_count),
            "memory_size": len(self.state.memory),
        }


# Example concrete agent
class EchoAgent(BaseAgent):
    """Example agent that echoes back task content"""

    async def process_task(self, task: Dict[str, Any]) -> Any:
        """Echo task content"""
        await asyncio.sleep(0.5)  # Simulate work

        return {"status": "completed", "echoed": task, "agent": self.agent_id}

    def get_system_prompt(self) -> str:
        """Get system prompt"""
        return "You are an echo agent. You repeat back what you receive."


# Example usage
if __name__ == "__main__":

    async def main():
        # Setup
        coordinator = AgentCoordinator()
        await coordinator.start()

        router = build_local_router()

        # Create agent
        agent = EchoAgent(
            agent_id="echo-1",
            agent_type="echo",
            capabilities=["echo"],
            coordinator=coordinator,
            provider_router=router,
            tier=Tier.LOCAL_FREE,
        )

        # Start agent
        await agent.start()

        # Assign task
        await coordinator.assign_task("echo-1", {"message": "Hello, agent!"})

        # Wait for result
        result = await coordinator.wait_for_result("echo-1", timeout=5)

        if result:
            print(f"Result: {result.content}")
        else:
            print("No result received")

        # Stats
        print(f"Agent stats: {agent.get_stats()}")

        # Cleanup
        await agent.stop()
        await coordinator.stop()

    asyncio.run(main())
