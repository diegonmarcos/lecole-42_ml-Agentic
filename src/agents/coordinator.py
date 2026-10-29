"""
Agent Coordinator - Message-driven multi-agent orchestration

Coordinates multiple agents using event-driven messaging pattern.
Based on AutoGen's multi-agent architecture.

Features:
- Event bus for agent communication
- Message routing and filtering
- Agent lifecycle management
- Concurrent agent execution (10+ agents)
- State tracking and persistence
"""

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Message types"""

    TASK_ASSIGNMENT = "task_assignment"
    TASK_RESULT = "task_result"
    AGENT_REQUEST = "agent_request"
    AGENT_RESPONSE = "agent_response"
    SYSTEM_EVENT = "system_event"
    ERROR = "error"


@dataclass
class Message:
    """Agent message"""

    message_id: str
    type: MessageType
    sender: str
    recipient: Optional[str]  # None = broadcast
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    parent_id: Optional[str] = None


@dataclass
class AgentInfo:
    """Agent registration info"""

    agent_id: str
    agent_type: str
    capabilities: List[str]
    status: str  # active, idle, busy, stopped
    message_count: int = 0
    last_activity: float = field(default_factory=time.time)


class EventBus:
    """
    Event bus for agent communication.

    Supports publish-subscribe pattern with message filtering.
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize event bus.

        Args:
            max_history: Maximum message history to keep
        """
        self.subscribers: Dict[str, List[Dict[str, Any]]] = {}
        self.message_history: deque = deque(maxlen=max_history)
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        agent_id: str,
        callback: Callable[[Message], Any],
        message_types: Optional[List[MessageType]] = None,
    ):
        """
        Subscribe to messages.

        Args:
            agent_id: Agent ID
            callback: Async callback function
            message_types: Filter by message types (None = all)
        """
        async with self._lock:
            if agent_id not in self.subscribers:
                self.subscribers[agent_id] = []

            self.subscribers[agent_id].append(
                {"callback": callback, "message_types": message_types}
            )

        logger.debug("Agent %s subscribed to event bus", agent_id)

    async def unsubscribe(self, agent_id: str):
        """Unsubscribe from messages"""
        async with self._lock:
            if agent_id in self.subscribers:
                del self.subscribers[agent_id]

        logger.debug("Agent %s unsubscribed from event bus", agent_id)

    async def publish(self, message: Message):
        """
        Publish message to event bus.

        Args:
            message: Message to publish
        """
        # Add to history
        self.message_history.append(message)

        # Determine recipients
        if message.recipient:
            # Direct message
            recipients = [message.recipient]
        else:
            # Broadcast
            recipients = list(self.subscribers.keys())

        # Deliver to subscribers
        tasks = []

        for recipient_id in recipients:
            if recipient_id == message.sender:
                continue  # Don't send to self

            if recipient_id in self.subscribers:
                for sub_info in self.subscribers[recipient_id]:
                    # Check message type filter
                    if (
                        sub_info["message_types"]
                        and message.type not in sub_info["message_types"]
                    ):
                        continue

                    # Call subscriber callback
                    task = asyncio.create_task(
                        self._safe_callback(sub_info["callback"], message)
                    )
                    tasks.append(task)

        # Wait for all deliveries
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_callback(self, callback: Callable, message: Message):
        """Safely execute callback with error handling"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(message)
            else:
                callback(message)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Callback error: %s", e, exc_info=True)

    def get_history(
        self,
        count: int = 100,
        message_type: Optional[MessageType] = None,
        sender: Optional[str] = None,
    ) -> List[Message]:
        """
        Get message history.

        Args:
            count: Number of messages to return
            message_type: Filter by type
            sender: Filter by sender

        Returns:
            List of messages (newest first)
        """
        messages = list(self.message_history)

        # Filter
        if message_type:
            messages = [m for m in messages if m.type == message_type]

        if sender:
            messages = [m for m in messages if m.sender == sender]

        # Return newest first
        return list(reversed(messages[-count:]))


class AgentCoordinator:
    """
    Coordinator for multi-agent system.

    Manages agent lifecycle, message routing, and task distribution.

    Usage:
        coordinator = AgentCoordinator()

        # Register agents
        await coordinator.register_agent("planner", "planner", ["planning"])
        await coordinator.register_agent("coder", "coder", ["coding"])

        # Start coordinator
        await coordinator.start()

        # Assign task
        await coordinator.assign_task("planner", {"instruction": "Plan feature X"})

        # Wait for completion
        result = await coordinator.wait_for_result("planner", timeout=60)

        # Stop
        await coordinator.stop()
    """

    def __init__(self):
        """Initialize coordinator"""
        self.event_bus = EventBus()
        self.agents: Dict[str, AgentInfo] = {}
        self.running = False
        self._lock = asyncio.Lock()

    async def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: List[str],
        callback: Optional[Callable] = None,
    ):
        """
        Register an agent.

        Args:
            agent_id: Unique agent ID
            agent_type: Agent type (planner, coder, reviewer, etc.)
            capabilities: Agent capabilities
            callback: Message callback function
        """
        async with self._lock:
            self.agents[agent_id] = AgentInfo(
                agent_id=agent_id,
                agent_type=agent_type,
                capabilities=capabilities,
                status="idle",
            )

        # Subscribe to messages
        if callback:
            await self.event_bus.subscribe(agent_id, callback)

        logger.info(
            "Registered agent: %s (%s) - %s", agent_id, agent_type, capabilities
        )

    async def unregister_agent(self, agent_id: str):
        """Unregister an agent"""
        await self.event_bus.unsubscribe(agent_id)

        async with self._lock:
            if agent_id in self.agents:
                del self.agents[agent_id]

        logger.info("Unregistered agent: %s", agent_id)

    async def start(self):
        """Start coordinator"""
        self.running = True
        logger.info("Agent coordinator started")

    async def stop(self):
        """Stop coordinator"""
        self.running = False
        logger.info("Agent coordinator stopped")

    async def assign_task(
        self, agent_id: str, task: Dict[str, Any], priority: int = 0
    ) -> str:
        """
        Assign task to agent.

        Args:
            agent_id: Target agent ID
            task: Task data
            priority: Task priority (higher = more important)

        Returns:
            Message ID
        """

        message_id = str(uuid.uuid4())

        message = Message(
            message_id=message_id,
            type=MessageType.TASK_ASSIGNMENT,
            sender="coordinator",
            recipient=agent_id,
            content=task,
            metadata={"priority": priority},
        )

        await self.event_bus.publish(message)

        # Update agent status
        async with self._lock:
            if agent_id in self.agents:
                self.agents[agent_id].status = "busy"
                self.agents[agent_id].message_count += 1
                self.agents[agent_id].last_activity = time.time()

        logger.info("Assigned task to %s: %s", agent_id, message_id)

        return message_id

    async def broadcast_event(self, event_type: str, data: Any):
        """
        Broadcast system event to all agents.

        Args:
            event_type: Event type
            data: Event data
        """

        message = Message(
            message_id=str(uuid.uuid4()),
            type=MessageType.SYSTEM_EVENT,
            sender="coordinator",
            recipient=None,  # Broadcast
            content={"event_type": event_type, "data": data},
        )

        await self.event_bus.publish(message)

    async def wait_for_result(
        self, agent_id: str, timeout: float = 60.0
    ) -> Optional[Message]:
        """
        Wait for task result from agent.

        Args:
            agent_id: Agent ID
            timeout: Timeout in seconds

        Returns:
            Result message or None if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check message history for results from this agent
            history = self.event_bus.get_history(
                count=10, message_type=MessageType.TASK_RESULT, sender=agent_id
            )

            if history:
                return history[0]  # Most recent

            await asyncio.sleep(0.1)

        logger.warning("Timeout waiting for result from %s", agent_id)
        return None

    def get_agent_status(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get agent status.

        Args:
            agent_id: Specific agent (None = all)

        Returns:
            Agent status dict
        """
        if agent_id:
            agent = self.agents.get(agent_id)
            if agent:
                return {
                    "agent_id": agent.agent_id,
                    "type": agent.agent_type,
                    "status": agent.status,
                    "capabilities": agent.capabilities,
                    "message_count": agent.message_count,
                    "last_activity": agent.last_activity,
                }
            return {}

        return {
            "total_agents": len(self.agents),
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "type": a.agent_type,
                    "status": a.status,
                    "message_count": a.message_count,
                }
                for a in self.agents.values()
            ],
        }

    def get_message_stats(self) -> Dict[str, Any]:
        """Get message statistics"""
        total_messages = len(self.event_bus.message_history)

        by_type: Dict[str, int] = {}
        for msg in self.event_bus.message_history:
            by_type[msg.type.value] = by_type.get(msg.type.value, 0) + 1

        return {
            "total_messages": total_messages,
            "by_type": by_type,
            "active_subscribers": len(self.event_bus.subscribers),
        }


# Example usage
if __name__ == "__main__":

    async def main():
        coordinator = AgentCoordinator()

        # Mock agent callback
        async def agent_callback(message: Message):
            print(f"Agent received: {message.type.value} from {message.sender}")

            # Simulate processing
            await asyncio.sleep(0.5)

            # Send result back
            result_msg = Message(
                message_id=f"result-{message.message_id}",
                type=MessageType.TASK_RESULT,
                sender=message.recipient or "",
                recipient=message.sender,
                content={"status": "completed", "result": "Success"},
                parent_id=message.message_id,
            )

            await coordinator.event_bus.publish(result_msg)

        # Register agents
        await coordinator.register_agent(
            "planner", "planner", ["planning"], agent_callback
        )
        await coordinator.register_agent("coder", "coder", ["coding"], agent_callback)
        await coordinator.register_agent(
            "reviewer", "reviewer", ["review"], agent_callback
        )

        # Start
        await coordinator.start()

        # Assign tasks
        await coordinator.assign_task("planner", {"task": "Plan feature"})
        await coordinator.assign_task("coder", {"task": "Write code"})

        # Wait for results
        result1 = await coordinator.wait_for_result("planner", timeout=5)
        result2 = await coordinator.wait_for_result("coder", timeout=5)

        print(f"\nPlanner result: {result1.content if result1 else 'None'}")
        print(f"Coder result: {result2.content if result2 else 'None'}")

        # Stats
        print(f"\nAgent status: {coordinator.get_agent_status()}")
        print(f"Message stats: {coordinator.get_message_stats()}")

        # Stop
        await coordinator.stop()

    asyncio.run(main())
