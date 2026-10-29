"""
Tool Registry - Dynamic tool discovery and execution system

Enables agents to discover and use available tools dynamically.
Supports MCP tools, Python functions, API endpoints, and custom tools.

Based on Dify and Flowise patterns for tool management.
"""

import asyncio
import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolType(Enum):
    """Tool types"""

    PYTHON_FUNCTION = "python_function"
    MCP_TOOL = "mcp_tool"
    API_ENDPOINT = "api_endpoint"
    BROWSER_ACTION = "browser_action"
    DATABASE_QUERY = "database_query"


@dataclass
class ToolParameter:
    """Tool parameter definition"""

    name: str
    type: str  # string, integer, boolean, array, object
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None


@dataclass
class Tool:
    """Tool definition"""

    name: str
    description: str
    tool_type: ToolType
    parameters: List[ToolParameter]
    handler: Callable
    category: str = "general"
    requires_auth: bool = False
    rate_limit: Optional[int] = None  # calls per minute
    timeout: int = 30  # seconds
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result from tool execution"""

    success: bool
    output: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """
    Central registry for all available tools.

    Usage:
        registry = ToolRegistry()

        # Register Python function
        @registry.register_function(
            description="Add two numbers",
            category="math"
        )
        async def add(a: int, b: int) -> int:
            return a + b

        # Execute tool
        result = await registry.execute("add", {"a": 5, "b": 3})
        print(result.output)  # 8

        # List available tools
        tools = registry.list_tools(category="math")
    """

    def __init__(self):
        """Initialize tool registry"""
        self.tools: Dict[str, Tool] = {}
        self._execution_counts: Dict[str, int] = {}
        self._last_execution: Dict[str, float] = {}

    def register_function(
        self,
        description: str,
        category: str = "general",
        requires_auth: bool = False,
        rate_limit: Optional[int] = None,
        timeout: int = 30,
    ):
        """
        Decorator to register a Python function as a tool.

        Args:
            description: Tool description
            category: Tool category
            requires_auth: Whether auth is required
            rate_limit: Rate limit (calls/min)
            timeout: Timeout in seconds

        Example:
            @registry.register_function(
                description="Search the web",
                category="search"
            )
            async def web_search(query: str, max_results: int = 10):
                # Implementation
                pass
        """

        def decorator(func: Callable) -> Callable:
            # Extract parameters from function signature
            sig = inspect.signature(func)
            parameters = []

            for param_name, param in sig.parameters.items():
                param_type = "string"  # default
                param_required = param.default == inspect.Parameter.empty

                # Try to infer type from annotation
                if param.annotation != inspect.Parameter.empty:
                    annotation = param.annotation
                    if annotation == int:
                        param_type = "integer"
                    elif annotation == bool:
                        param_type = "boolean"
                    elif annotation == float:
                        param_type = "number"
                    elif annotation in (list, List):
                        param_type = "array"
                    elif annotation in (dict, Dict):
                        param_type = "object"

                parameters.append(
                    ToolParameter(
                        name=param_name,
                        type=param_type,
                        description=f"Parameter: {param_name}",
                        required=param_required,
                        default=param.default
                        if param.default != inspect.Parameter.empty
                        else None,
                    )
                )

            # Register tool
            tool = Tool(
                name=func.__name__,
                description=description,
                tool_type=ToolType.PYTHON_FUNCTION,
                parameters=parameters,
                handler=func,
                category=category,
                requires_auth=requires_auth,
                rate_limit=rate_limit,
                timeout=timeout,
            )

            self.tools[func.__name__] = tool
            logger.info("Registered tool: %s (%s)", func.__name__, category)

            return func

        return decorator

    def register_tool(self, tool: Tool):
        """
        Register a tool manually.

        Args:
            tool: Tool instance
        """
        self.tools[tool.name] = tool
        logger.info("Registered tool: %s (%s)", tool.name, tool.category)

    def unregister(self, name: str):
        """
        Unregister a tool.

        Args:
            name: Tool name
        """
        if name in self.tools:
            del self.tools[name]
            logger.info("Unregistered tool: %s", name)

    def get_tool(self, name: str) -> Optional[Tool]:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None
        """
        return self.tools.get(name)

    def list_tools(
        self, category: Optional[str] = None, tool_type: Optional[ToolType] = None
    ) -> List[Tool]:
        """
        List available tools.

        Args:
            category: Filter by category
            tool_type: Filter by type

        Returns:
            List of tools
        """
        tools = list(self.tools.values())

        if category:
            tools = [t for t in tools if t.category == category]

        if tool_type:
            tools = [t for t in tools if t.tool_type == tool_type]

        return tools

    def get_tool_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get tool schema in OpenAI function calling format.

        Args:
            name: Tool name

        Returns:
            Tool schema dict
        """
        tool = self.get_tool(name)
        if not tool:
            return None

        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param in tool.parameters:
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }

            if param.enum:
                prop["enum"] = param.enum

            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """
        Get schemas for all tools.

        Returns:
            List of tool schemas
        """
        schemas = [self.get_tool_schema(name) for name in self.tools]
        return [schema for schema in schemas if schema is not None]

    async def execute(  # pylint: disable=unused-argument
        self,
        name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Execute a tool.

        Args:
            name: Tool name
            parameters: Tool parameters
            context: Execution context (user_id, auth, etc.)

        Returns:
            ToolResult with output
        """

        start_time = time.time()

        # Get tool
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(
                success=False, output=None, error=f"Tool not found: {name}"
            )

        # Check rate limit
        if tool.rate_limit:
            current_time = time.time()
            last_exec = self._last_execution.get(name, 0)

            if current_time - last_exec < (60.0 / tool.rate_limit):
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Rate limit exceeded for {name}",
                    execution_time=time.time() - start_time,
                )

        # Validate parameters
        for param in tool.parameters:
            if param.required and param.name not in parameters:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Missing required parameter: {param.name}",
                    execution_time=time.time() - start_time,
                )

        # Execute tool
        try:
            # Check if handler is async
            if asyncio.iscoroutinefunction(tool.handler):
                output = await asyncio.wait_for(
                    tool.handler(**parameters), timeout=tool.timeout
                )
            else:
                output = tool.handler(**parameters)

            # Update stats
            self._execution_counts[name] = self._execution_counts.get(name, 0) + 1
            self._last_execution[name] = time.time()

            return ToolResult(
                success=True,
                output=output,
                execution_time=time.time() - start_time,
                metadata={"execution_count": self._execution_counts[name]},
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool execution timeout ({tool.timeout}s)",
                execution_time=time.time() - start_time,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Tool execution error (%s): %s", name, e, exc_info=True)
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                execution_time=time.time() - start_time,
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Stats dict
        """
        return {
            "total_tools": len(self.tools),
            "tools_by_category": {
                category: len(
                    [t for t in self.tools.values() if t.category == category]
                )
                for category in set(t.category for t in self.tools.values())
            },
            "execution_counts": dict(self._execution_counts),
            "most_used": sorted(
                self._execution_counts.items(), key=lambda x: x[1], reverse=True
            )[:10],
        }


# Global registry instance
_global_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Get global tool registry"""
    return _global_registry


# Example tools
if __name__ == "__main__":

    async def main():
        registry = ToolRegistry()

        # Register some example tools
        @registry.register_function(
            description="Add two numbers together", category="math"
        )
        async def add(a: int, b: int) -> int:
            """Add two numbers"""
            await asyncio.sleep(0.1)  # Simulate work
            return a + b

        @registry.register_function(
            description="Search for items",
            category="search",
            rate_limit=10,  # 10 calls per minute
        )
        async def search(query: str, max_results: int = 10) -> List[str]:
            """Search for items"""
            await asyncio.sleep(0.2)
            return [f"Result {i+1} for '{query}'" for i in range(max_results)]

        # List tools
        print(f"Registered tools: {len(registry.tools)}")
        for tool in registry.list_tools():
            print(f"  - {tool.name}: {tool.description}")

        # Get schema
        print("\nTool schema for 'add':")
        print(json.dumps(registry.get_tool_schema("add"), indent=2))

        # Execute tools
        result1 = await registry.execute("add", {"a": 5, "b": 3})
        print(f"\nadd(5, 3) = {result1.output} (took {result1.execution_time:.3f}s)")

        result2 = await registry.execute("search", {"query": "test", "max_results": 3})
        print("\nsearch('test', 3):")
        for item in result2.output:
            print(f"  - {item}")

        # Stats
        print("\nRegistry stats:")
        stats = registry.get_stats()
        print(f"  Total tools: {stats['total_tools']}")
        print(f"  Most used: {stats['most_used']}")

    asyncio.run(main())
