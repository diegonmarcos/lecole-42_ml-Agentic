"""
Workflow Versioning System - TASK-035

Provides semantic versioning for agent workflows with:
- Version storage and retrieval (Redis + filesystem)
- Rollback capabilities
- Version comparison and diff
- Immutable version snapshots
- Version metadata (author, timestamp, changelog)
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class VersionStatus(Enum):
    """Version status"""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class WorkflowVersion:
    """Workflow version metadata"""

    workflow_id: str
    version: str  # Semantic version (e.g., "1.2.3")
    status: VersionStatus
    created_at: datetime
    author: str
    changelog: str
    workflow_data: Dict[str, Any]
    checksum: str  # SHA-256 of workflow_data
    parent_version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization"""
        data = asdict(self)
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowVersion":
        """Create from dict"""
        data["status"] = VersionStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


@dataclass
class VersionComparison:
    """Comparison between two workflow versions"""

    old_version: str
    new_version: str
    changes: List[Dict[str, Any]]
    breaking_changes: List[str]
    compatible: bool


class WorkflowVersionManager:
    """
    Manages workflow versioning with Redis + filesystem storage.

    Usage:
        manager = WorkflowVersionManager(redis_client)

        # Create new version
        version = await manager.create_version(
            workflow_id="agent-pipeline-1",
            version="1.0.0",
            workflow_data={...},
            author="system",
            changelog="Initial version"
        )

        # Get version
        version = await manager.get_version("agent-pipeline-1", "1.0.0")

        # List versions
        versions = await manager.list_versions("agent-pipeline-1")

        # Rollback
        await manager.rollback("agent-pipeline-1", "1.0.0")
    """

    def __init__(self, redis_client: redis.Redis, storage_path: str = "data/workflows"):
        """
        Initialize version manager.

        Args:
            redis_client: Redis client for metadata
            storage_path: Filesystem path for version storage
        """
        self.redis = redis_client
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _calculate_checksum(self, workflow_data: Dict[str, Any]) -> str:
        """Calculate SHA-256 checksum of workflow data"""
        data_str = json.dumps(workflow_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def _get_redis_key(self, workflow_id: str, version: str) -> str:
        """Get Redis key for version metadata"""
        return f"workflow:version:{workflow_id}:{version}"

    def _get_active_key(self, workflow_id: str) -> str:
        """Get Redis key for active version"""
        return f"workflow:active:{workflow_id}"

    def _get_versions_key(self, workflow_id: str) -> str:
        """Get Redis key for version list"""
        return f"workflow:versions:{workflow_id}"

    def _get_storage_path(self, workflow_id: str, version: str) -> Path:
        """Get filesystem path for workflow data"""
        return self.storage_path / workflow_id / f"{version}.json"

    async def create_version(
        self,
        workflow_id: str,
        version: str,
        workflow_data: Dict[str, Any],
        author: str,
        changelog: str,
        parent_version: Optional[str] = None,
        set_active: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkflowVersion:
        """
        Create new workflow version.

        Args:
            workflow_id: Unique workflow identifier
            version: Semantic version string (e.g., "1.2.3")
            workflow_data: Complete workflow definition
            author: Version author
            changelog: Change description
            parent_version: Previous version (for lineage)
            set_active: Set as active version
            metadata: Additional metadata

        Returns:
            WorkflowVersion object
        """
        # Validate semantic version
        if not self._validate_semver(version):
            raise ValueError(f"Invalid semantic version: {version}")

        # Check if version already exists
        existing = await self.get_version(workflow_id, version)
        if existing:
            raise ValueError(
                f"Version {version} already exists for workflow {workflow_id}"
            )

        # Calculate checksum
        checksum = self._calculate_checksum(workflow_data)

        # Create version object
        workflow_version = WorkflowVersion(
            workflow_id=workflow_id,
            version=version,
            status=VersionStatus.ACTIVE if set_active else VersionStatus.DRAFT,
            created_at=datetime.utcnow(),
            author=author,
            changelog=changelog,
            workflow_data=workflow_data,
            checksum=checksum,
            parent_version=parent_version,
            metadata=metadata or {},
        )

        # Store workflow data on filesystem
        storage_path = self._get_storage_path(workflow_id, version)
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(workflow_data, f, indent=2)

        # Store metadata in Redis
        redis_key = self._get_redis_key(workflow_id, version)
        version_dict = workflow_version.to_dict()
        # Don't store large workflow_data in Redis
        version_dict.pop("workflow_data")

        await self.redis.set(
            redis_key, json.dumps(version_dict), ex=86400 * 365  # 1 year expiry
        )

        # Add to version list
        versions_key = self._get_versions_key(workflow_id)
        await self.redis.zadd(versions_key, {version: datetime.utcnow().timestamp()})

        # Set as active if requested
        if set_active:
            active_key = self._get_active_key(workflow_id)
            await self.redis.set(active_key, version)

        logger.info("Created workflow version: %s v%s", workflow_id, version)

        return workflow_version

    async def get_version(
        self, workflow_id: str, version: str
    ) -> Optional[WorkflowVersion]:
        """Get specific workflow version"""
        # Get metadata from Redis
        redis_key = self._get_redis_key(workflow_id, version)
        data = await self.redis.get(redis_key)

        if not data:
            return None

        version_dict = json.loads(data)

        # Load workflow data from filesystem
        storage_path = self._get_storage_path(workflow_id, version)

        if not storage_path.exists():
            logger.warning("Workflow data not found: %s", storage_path)
            return None

        with open(storage_path, "r", encoding="utf-8") as f:
            workflow_data = json.load(f)

        version_dict["workflow_data"] = workflow_data

        return WorkflowVersion.from_dict(version_dict)

    async def get_active_version(self, workflow_id: str) -> Optional[WorkflowVersion]:
        """Get currently active version"""
        active_key = self._get_active_key(workflow_id)
        version = await self.redis.get(active_key)

        if not version:
            return None

        if isinstance(version, bytes):
            version = version.decode()

        return await self.get_version(workflow_id, version)

    async def list_versions(
        self, workflow_id: str, status: Optional[VersionStatus] = None, limit: int = 100
    ) -> List[WorkflowVersion]:
        """
        List workflow versions.

        Args:
            workflow_id: Workflow identifier
            status: Filter by status
            limit: Maximum versions to return

        Returns:
            List of WorkflowVersion objects (newest first)
        """
        versions_key = self._get_versions_key(workflow_id)

        # Get version list from sorted set (newest first)
        version_strings = await self.redis.zrevrange(versions_key, 0, limit - 1)

        versions = []
        for version_str in version_strings:
            if isinstance(version_str, bytes):
                version_str = version_str.decode()

            version = await self.get_version(workflow_id, version_str)
            if version:
                if status is None or version.status == status:
                    versions.append(version)

        return versions

    async def set_active_version(self, workflow_id: str, version: str) -> bool:
        """
        Set active version (rollback/rollforward).

        Args:
            workflow_id: Workflow identifier
            version: Version to activate

        Returns:
            True if successful
        """
        # Verify version exists
        workflow_version = await self.get_version(workflow_id, version)
        if not workflow_version:
            raise ValueError(f"Version {version} not found")

        # Update active version
        active_key = self._get_active_key(workflow_id)
        await self.redis.set(active_key, version)

        # Update version status
        redis_key = self._get_redis_key(workflow_id, version)
        data = await self.redis.get(redis_key)
        if data:
            version_dict = json.loads(data)
            version_dict["status"] = VersionStatus.ACTIVE.value
            await self.redis.set(redis_key, json.dumps(version_dict))

        logger.info("Set active version: %s v%s", workflow_id, version)
        return True

    async def rollback(
        self, workflow_id: str, target_version: str
    ) -> Optional[WorkflowVersion]:
        """
        Rollback to previous version.

        Args:
            workflow_id: Workflow identifier
            target_version: Version to rollback to

        Returns:
            Activated WorkflowVersion
        """
        await self.set_active_version(workflow_id, target_version)
        version = await self.get_version(workflow_id, target_version)

        logger.info("Rolled back workflow %s to v%s", workflow_id, target_version)

        return version

    async def compare_versions(
        self, workflow_id: str, old_version: str, new_version: str
    ) -> VersionComparison:
        """
        Compare two workflow versions.

        Args:
            workflow_id: Workflow identifier
            old_version: Old version
            new_version: New version

        Returns:
            VersionComparison with changes
        """
        old = await self.get_version(workflow_id, old_version)
        new = await self.get_version(workflow_id, new_version)

        if not old or not new:
            raise ValueError("Version not found")

        changes = self._diff_workflows(old.workflow_data, new.workflow_data)
        breaking_changes = self._detect_breaking_changes(changes)

        return VersionComparison(
            old_version=old_version,
            new_version=new_version,
            changes=changes,
            breaking_changes=breaking_changes,
            compatible=len(breaking_changes) == 0,
        )

    def _validate_semver(self, version: str) -> bool:
        """Validate semantic version format"""
        parts = version.split(".")
        if len(parts) != 3:
            return False

        try:
            major, minor, patch = map(int, parts)
            return major >= 0 and minor >= 0 and patch >= 0
        except ValueError:
            return False

    def _diff_workflows(
        self, old_data: Dict[str, Any], new_data: Dict[str, Any], path: str = ""
    ) -> List[Dict[str, Any]]:
        """Recursively diff workflow data"""
        changes = []

        # Check for removed keys
        for key in old_data:
            if key not in new_data:
                changes.append(
                    {
                        "type": "removed",
                        "path": f"{path}.{key}" if path else key,
                        "old_value": old_data[key],
                    }
                )

        # Check for added/modified keys
        for key in new_data:
            new_path = f"{path}.{key}" if path else key

            if key not in old_data:
                changes.append(
                    {"type": "added", "path": new_path, "new_value": new_data[key]}
                )
            elif old_data[key] != new_data[key]:
                if isinstance(old_data[key], dict) and isinstance(new_data[key], dict):
                    # Recurse into nested dicts
                    changes.extend(
                        self._diff_workflows(old_data[key], new_data[key], new_path)
                    )
                else:
                    changes.append(
                        {
                            "type": "modified",
                            "path": new_path,
                            "old_value": old_data[key],
                            "new_value": new_data[key],
                        }
                    )

        return changes

    def _detect_breaking_changes(self, changes: List[Dict[str, Any]]) -> List[str]:
        """Detect breaking changes"""
        breaking = []

        for change in changes:
            # Breaking: Removed fields
            if change["type"] == "removed":
                breaking.append(f"Removed: {change['path']}")

            # Breaking: Changed types
            elif change["type"] == "modified":
                if type(change["old_value"]) is not type(change["new_value"]):
                    breaking.append(f"Type changed: {change['path']}")

        return breaking

    async def deprecate_version(self, workflow_id: str, version: str) -> bool:
        """Mark version as deprecated"""
        redis_key = self._get_redis_key(workflow_id, version)
        data = await self.redis.get(redis_key)

        if not data:
            return False

        version_dict = json.loads(data)
        version_dict["status"] = VersionStatus.DEPRECATED.value
        await self.redis.set(redis_key, json.dumps(version_dict))

        logger.info("Deprecated version: %s v%s", workflow_id, version)
        return True

    async def get_version_history(
        self, workflow_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get version history with metadata.

        Returns:
            List of version metadata (newest first)
        """
        versions = await self.list_versions(workflow_id, limit=limit)

        history = []
        for version in versions:
            history.append(
                {
                    "version": version.version,
                    "status": version.status.value,
                    "created_at": version.created_at.isoformat(),
                    "author": version.author,
                    "changelog": version.changelog,
                    "parent_version": version.parent_version,
                    "checksum": version.checksum,
                }
            )

        return history


# Example usage
if __name__ == "__main__":

    async def main():
        # Initialize Redis
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

        manager = WorkflowVersionManager(redis_client)

        # Create version 1.0.0
        workflow_data_v1 = {
            "agents": ["planner", "coder"],
            "steps": [
                {"agent": "planner", "action": "plan_task"},
                {"agent": "coder", "action": "generate_code"},
            ],
        }

        v1 = await manager.create_version(
            workflow_id="code-generation-pipeline",
            version="1.0.0",
            workflow_data=workflow_data_v1,
            author="system",
            changelog="Initial version with planner + coder",
        )

        print(f"Created v1.0.0: {v1.checksum}")

        # Create version 1.1.0 (add reviewer)
        workflow_data_v2 = {
            "agents": ["planner", "coder", "reviewer"],
            "steps": [
                {"agent": "planner", "action": "plan_task"},
                {"agent": "coder", "action": "generate_code"},
                {"agent": "reviewer", "action": "review_code"},
            ],
        }

        v2 = await manager.create_version(
            workflow_id="code-generation-pipeline",
            version="1.1.0",
            workflow_data=workflow_data_v2,
            author="system",
            changelog="Add reviewer agent",
            parent_version="1.0.0",
        )

        print(f"Created v1.1.0: {v2.checksum}")

        # Compare versions
        comparison = await manager.compare_versions(
            "code-generation-pipeline", "1.0.0", "1.1.0"
        )

        print(f"\nChanges: {len(comparison.changes)}")
        print(f"Breaking changes: {comparison.breaking_changes}")
        print(f"Compatible: {comparison.compatible}")

        # List versions
        versions = await manager.list_versions("code-generation-pipeline")
        print(f"\nVersions: {[v.version for v in versions]}")

        # Get active version
        active = await manager.get_active_version("code-generation-pipeline")
        print(f"Active version: {active.version}")

        # Rollback
        await manager.rollback("code-generation-pipeline", "1.0.0")
        active = await manager.get_active_version("code-generation-pipeline")
        print(f"After rollback: {active.version}")

        await redis_client.close()

    asyncio.run(main())
