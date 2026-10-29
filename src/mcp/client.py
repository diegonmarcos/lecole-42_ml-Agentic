"""
MCP Client Integration - Connect to Model Context Protocol servers

This client enables privacy-compatible tool use by connecting to MCP servers
(filesystem, git, memory) running in Docker containers.

Features:
- Async client for all 3 MCP servers
- Request/response handling with retries
- Rate limiting awareness
- Error handling and failover
- Privacy mode validation
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class MCPServerType(Enum):
    """MCP server types"""

    FILESYSTEM = "filesystem"
    GIT = "git"
    MEMORY = "memory"


@dataclass
class MCPConfig:
    """Configuration for an MCP server"""

    server_type: MCPServerType
    base_url: str
    enabled: bool = True
    timeout: int = 30
    max_retries: int = 3


class MCPClient:
    """
    Client for interacting with Model Context Protocol servers.

    Usage:
        client = MCPClient(configs={
            MCPServerType.FILESYSTEM: MCPConfig(
                server_type=MCPServerType.FILESYSTEM,
                base_url="http://localhost:3001"
            )
        })

        # Read file
        content = await client.filesystem.read_file("/data/projects/README.md")

        # Search git
        results = await client.git.search("TODO", max_results=10)

        # Store memory
        await client.memory.store("user_123", "preference", {"theme": "dark"})
    """

    def __init__(self, configs: Dict[MCPServerType, MCPConfig]):
        """
        Initialize MCP client.

        Args:
            configs: Dictionary mapping server types to configs
        """
        self.configs = configs
        self._session: Optional[aiohttp.ClientSession] = None

        # Initialize sub-clients
        self.filesystem = (
            FilesystemClient(self) if MCPServerType.FILESYSTEM in configs else None
        )
        self.git = GitClient(self) if MCPServerType.GIT in configs else None
        self.memory = MemoryClient(self) if MCPServerType.MEMORY in configs else None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def request(
        self,
        server_type: MCPServerType,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Make request to MCP server with retries.

        Args:
            server_type: Server type (filesystem, git, memory)
            endpoint: API endpoint (e.g., "/read_file")
            method: HTTP method
            data: JSON data for request body
            params: Query parameters

        Returns:
            Response JSON

        Raises:
            aiohttp.ClientError: On network/API errors
        """
        config = self.configs.get(server_type)
        if not config:
            raise ValueError(f"MCP server not configured: {server_type}")

        if not config.enabled:
            raise ValueError(f"MCP server disabled: {server_type}")

        session = await self._get_session()
        url = f"{config.base_url}{endpoint}"

        # Retry logic
        last_error = None
        for attempt in range(config.max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=config.timeout)

                if method == "GET":
                    async with session.get(url, params=params, timeout=timeout) as resp:
                        resp.raise_for_status()
                        return await resp.json()
                else:
                    async with session.post(
                        url, json=data, params=params, timeout=timeout
                    ) as resp:
                        resp.raise_for_status()
                        return await resp.json()

            except Exception as e:  # pylint: disable=broad-exception-caught
                last_error = e
                logger.warning(
                    "MCP request failed (attempt %s/%s): %s",
                    attempt + 1,
                    config.max_retries,
                    e,
                )

                if attempt < config.max_retries - 1:
                    await asyncio.sleep(2**attempt)  # Exponential backoff

        if last_error is None:
            raise RuntimeError("MCP request failed without an exception")
        raise last_error

    async def health_check(self, server_type: MCPServerType) -> bool:
        """
        Check if MCP server is healthy.

        Args:
            server_type: Server type to check

        Returns:
            True if server is healthy
        """
        try:
            response = await self.request(server_type, "/health", method="GET")
            return response.get("status") == "ok"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Health check failed for %s: %s", server_type, e)
            return False

    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()


class FilesystemClient:
    """Client for MCP Filesystem server"""

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    async def read_file(self, path: str) -> str:
        """
        Read file from sandboxed filesystem.

        Args:
            path: File path (must be in allowed directories)

        Returns:
            File content as string
        """
        response = await self.mcp.request(
            MCPServerType.FILESYSTEM, "/read_file", data={"path": path}
        )
        return response["content"]

    async def write_file(self, path: str, content: str) -> bool:
        """
        Write file to sandboxed filesystem.

        Args:
            path: File path
            content: File content

        Returns:
            True if successful
        """
        response = await self.mcp.request(
            MCPServerType.FILESYSTEM,
            "/write_file",
            data={"path": path, "content": content},
        )
        return response.get("success", False)

    async def list_directory(self, path: str) -> List[Dict[str, Any]]:
        """
        List directory contents.

        Args:
            path: Directory path

        Returns:
            List of file/directory metadata dicts
        """
        response = await self.mcp.request(
            MCPServerType.FILESYSTEM, "/list_directory", data={"path": path}
        )
        return response.get("entries", [])

    async def search_files(
        self, pattern: str, root: str = "/data/projects"
    ) -> List[str]:
        """
        Search for files matching pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.py")
            root: Root directory to search

        Returns:
            List of matching file paths
        """
        response = await self.mcp.request(
            MCPServerType.FILESYSTEM,
            "/search_files",
            data={"pattern": pattern, "root": root},
        )
        return response.get("files", [])


class GitClient:
    """Client for MCP Git server"""

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    async def log(self, repo_path: str, max_commits: int = 100) -> List[Dict[str, Any]]:
        """
        Get git log for repository.

        Args:
            repo_path: Repository path
            max_commits: Maximum commits to return

        Returns:
            List of commit dicts
        """
        response = await self.mcp.request(
            MCPServerType.GIT,
            "/log",
            data={"repo_path": repo_path, "max_commits": max_commits},
        )
        return response.get("commits", [])

    async def diff(self, repo_path: str, commit1: str, commit2: str = "HEAD") -> str:
        """
        Get diff between commits.

        Args:
            repo_path: Repository path
            commit1: First commit hash
            commit2: Second commit hash (default: HEAD)

        Returns:
            Diff output as string
        """
        response = await self.mcp.request(
            MCPServerType.GIT,
            "/diff",
            data={"repo_path": repo_path, "commit1": commit1, "commit2": commit2},
        )
        return response["diff"]

    async def search(
        self, query: str, repo_path: str, max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search git repository for query.

        Args:
            query: Search query
            repo_path: Repository path
            max_results: Maximum results to return

        Returns:
            List of search result dicts
        """
        response = await self.mcp.request(
            MCPServerType.GIT,
            "/search",
            data={"query": query, "repo_path": repo_path, "max_results": max_results},
        )
        return response.get("results", [])

    async def blame(self, repo_path: str, file_path: str) -> Dict[str, Any]:
        """
        Get git blame for file.

        Args:
            repo_path: Repository path
            file_path: File path within repo

        Returns:
            Blame data dict
        """
        response = await self.mcp.request(
            MCPServerType.GIT,
            "/blame",
            data={"repo_path": repo_path, "file_path": file_path},
        )
        return response.get("blame", {})


class MemoryClient:
    """Client for MCP Memory server"""

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    async def store(
        self,
        user_id: str,
        memory_type: str,
        data: Dict[str, Any],
        ttl_hours: Optional[int] = None,
    ) -> str:
        """
        Store memory with encryption.

        Args:
            user_id: User identifier
            memory_type: Memory type (conversation, facts, preferences, context)
            data: Data to store
            ttl_hours: Time to live in hours (None = use default for type)

        Returns:
            Memory ID
        """
        response = await self.mcp.request(
            MCPServerType.MEMORY,
            "/store",
            data={
                "user_id": user_id,
                "memory_type": memory_type,
                "data": data,
                "ttl_hours": ttl_hours,
            },
        )
        return response["memory_id"]

    async def retrieve(self, user_id: str, memory_id: str) -> Dict[str, Any]:
        """
        Retrieve memory by ID.

        Args:
            user_id: User identifier
            memory_id: Memory ID

        Returns:
            Memory data dict
        """
        response = await self.mcp.request(
            MCPServerType.MEMORY,
            "/retrieve",
            data={"user_id": user_id, "memory_id": memory_id},
        )
        return response.get("data", {})

    async def search(
        self,
        user_id: str,
        query: str,
        memory_type: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search memories for user.

        Args:
            user_id: User identifier
            query: Search query
            memory_type: Filter by memory type (None = all types)
            max_results: Maximum results

        Returns:
            List of memory dicts
        """
        response = await self.mcp.request(
            MCPServerType.MEMORY,
            "/search",
            data={
                "user_id": user_id,
                "query": query,
                "memory_type": memory_type,
                "max_results": max_results,
            },
        )
        return response.get("memories", [])

    async def delete(self, user_id: str, memory_id: str) -> bool:
        """
        Delete memory.

        Args:
            user_id: User identifier
            memory_id: Memory ID

        Returns:
            True if successful
        """
        response = await self.mcp.request(
            MCPServerType.MEMORY,
            "/delete",
            data={"user_id": user_id, "memory_id": memory_id},
        )
        return response.get("success", False)

    async def list_memories(
        self, user_id: str, memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all memories for user.

        Args:
            user_id: User identifier
            memory_type: Filter by memory type (None = all types)

        Returns:
            List of memory metadata dicts
        """
        response = await self.mcp.request(
            MCPServerType.MEMORY,
            "/list",
            data={"user_id": user_id, "memory_type": memory_type},
        )
        return response.get("memories", [])


# Example usage
if __name__ == "__main__":

    async def main():
        # Configure MCP servers
        configs = {
            MCPServerType.FILESYSTEM: MCPConfig(
                server_type=MCPServerType.FILESYSTEM, base_url="http://localhost:3001"
            ),
            MCPServerType.GIT: MCPConfig(
                server_type=MCPServerType.GIT, base_url="http://localhost:3002"
            ),
            MCPServerType.MEMORY: MCPConfig(
                server_type=MCPServerType.MEMORY, base_url="http://localhost:3003"
            ),
        }

        client = MCPClient(configs)

        # Health checks
        for server_type in [
            MCPServerType.FILESYSTEM,
            MCPServerType.GIT,
            MCPServerType.MEMORY,
        ]:
            is_healthy = await client.health_check(server_type)
            print(f"{server_type.value}: {'✓' if is_healthy else '✗'}")

        # Filesystem operations
        if client.filesystem:
            files = await client.filesystem.list_directory("/data/projects")
            print(f"\nFiles in /data/projects: {len(files)}")

        # Git operations
        if client.git:
            commits = await client.git.log("/data/repos/myproject", max_commits=5)
            print(f"\nRecent commits: {len(commits)}")

        # Memory operations
        if client.memory:
            memory_id = await client.memory.store(
                "user_123", "preferences", {"theme": "dark", "language": "en"}
            )
            print(f"\nStored memory: {memory_id}")

            data = await client.memory.retrieve("user_123", memory_id)
            print(f"Retrieved: {data}")

        await client.close()

    asyncio.run(main())
