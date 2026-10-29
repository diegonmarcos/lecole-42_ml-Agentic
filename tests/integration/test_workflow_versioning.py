"""
Integration tests for workflow versioning and A/B testing - TASK-035/036
"""

import pytest

try:
    import redis.asyncio as redis
except ImportError:
    import redis

from src.workflows.versioning import (
    WorkflowVersionManager,
    VersionStatus,
)
from src.workflows.ab_testing import (
    ABTestingManager,
    Variant,
    ExperimentStatus,
)


@pytest.fixture
async def redis_client():
    """Redis client fixture"""
    client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    yield client
    await client.close()


@pytest.fixture
async def version_manager(redis_client):
    """Version manager fixture"""
    return WorkflowVersionManager(redis_client, storage_path="data/test_workflows")


@pytest.fixture
async def ab_manager(redis_client, version_manager):
    """A/B testing manager fixture"""
    return ABTestingManager(redis_client, version_manager)


class TestWorkflowVersioning:
    """Test workflow versioning system"""

    @pytest.mark.asyncio
    async def test_create_version(self, version_manager):
        """Test creating workflow version"""
        workflow_data = {
            "agents": ["planner", "coder"],
            "steps": [
                {"agent": "planner", "action": "plan"},
                {"agent": "coder", "action": "code"},
            ],
        }

        version = await version_manager.create_version(
            workflow_id="test-workflow-1",
            version="1.0.0",
            workflow_data=workflow_data,
            author="test",
            changelog="Initial version",
        )

        assert version.version == "1.0.0"
        assert version.workflow_id == "test-workflow-1"
        assert version.status == VersionStatus.ACTIVE
        assert version.checksum is not None
        assert len(version.checksum) == 64  # SHA-256

    @pytest.mark.asyncio
    async def test_get_version(self, version_manager):
        """Test retrieving workflow version"""
        # Create version
        workflow_data = {"agents": ["planner"]}

        await version_manager.create_version(
            workflow_id="test-workflow-2",
            version="1.0.0",
            workflow_data=workflow_data,
            author="test",
            changelog="Test",
        )

        # Get version
        version = await version_manager.get_version("test-workflow-2", "1.0.0")

        assert version is not None
        assert version.version == "1.0.0"
        assert version.workflow_data == workflow_data

    @pytest.mark.asyncio
    async def test_get_active_version(self, version_manager):
        """Test getting active version"""
        workflow_data_v1 = {"agents": ["planner"]}
        workflow_data_v2 = {"agents": ["planner", "coder"]}

        # Create v1.0.0
        await version_manager.create_version(
            workflow_id="test-workflow-3",
            version="1.0.0",
            workflow_data=workflow_data_v1,
            author="test",
            changelog="v1",
        )

        # Create v2.0.0 (sets as active)
        await version_manager.create_version(
            workflow_id="test-workflow-3",
            version="2.0.0",
            workflow_data=workflow_data_v2,
            author="test",
            changelog="v2",
            set_active=True,
        )

        # Get active
        active = await version_manager.get_active_version("test-workflow-3")

        assert active is not None
        assert active.version == "2.0.0"
        assert active.workflow_data == workflow_data_v2

    @pytest.mark.asyncio
    async def test_list_versions(self, version_manager):
        """Test listing workflow versions"""
        workflow_id = "test-workflow-4"

        # Create multiple versions
        for i in range(3):
            await version_manager.create_version(
                workflow_id=workflow_id,
                version=f"1.{i}.0",
                workflow_data={"version": i},
                author="test",
                changelog=f"Version {i}",
                set_active=(i == 2),  # Last one active
            )

        # List versions
        versions = await version_manager.list_versions(workflow_id)

        assert len(versions) == 3
        # Newest first
        assert versions[0].version == "1.2.0"
        assert versions[1].version == "1.1.0"
        assert versions[2].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_rollback(self, version_manager):
        """Test rolling back to previous version"""
        workflow_id = "test-workflow-5"

        # Create v1.0.0
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={"version": 1},
            author="test",
            changelog="v1",
        )

        # Create v2.0.0
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={"version": 2},
            author="test",
            changelog="v2",
            set_active=True,
        )

        # Verify v2 is active
        active = await version_manager.get_active_version(workflow_id)
        assert active.version == "2.0.0"

        # Rollback to v1
        await version_manager.rollback(workflow_id, "1.0.0")

        # Verify v1 is now active
        active = await version_manager.get_active_version(workflow_id)
        assert active.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_compare_versions(self, version_manager):
        """Test version comparison"""
        workflow_id = "test-workflow-6"

        # Create v1 (2 agents)
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={"agents": ["planner", "coder"], "timeout": 30},
            author="test",
            changelog="v1",
        )

        # Create v2 (3 agents, different timeout)
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={"agents": ["planner", "coder", "reviewer"], "timeout": 60},
            author="test",
            changelog="v2",
        )

        # Compare
        comparison = await version_manager.compare_versions(
            workflow_id, "1.0.0", "2.0.0"
        )

        assert len(comparison.changes) > 0

        # Check for agent list change
        agent_changes = [c for c in comparison.changes if "agents" in c["path"]]
        assert len(agent_changes) > 0

    @pytest.mark.asyncio
    async def test_version_checksum(self, version_manager):
        """Test that identical workflow data produces same checksum"""
        workflow_id = "test-workflow-7"

        workflow_data = {
            "agents": ["planner", "coder"],
            "steps": [{"agent": "planner"}],
        }

        # Create v1
        v1 = await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data=workflow_data.copy(),
            author="test",
            changelog="v1",
        )

        # Create v2 with identical data
        v2 = await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.1",
            workflow_data=workflow_data.copy(),
            author="test",
            changelog="v1.0.1",
        )

        # Checksums should match
        assert v1.checksum == v2.checksum

    @pytest.mark.asyncio
    async def test_deprecate_version(self, version_manager):
        """Test deprecating a version"""
        workflow_id = "test-workflow-8"

        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={"agents": []},
            author="test",
            changelog="test",
        )

        # Deprecate
        success = await version_manager.deprecate_version(workflow_id, "1.0.0")
        assert success

        # Verify status
        version = await version_manager.get_version(workflow_id, "1.0.0")
        assert version.status == VersionStatus.DEPRECATED


class TestABTesting:
    """Test A/B testing framework"""

    @pytest.mark.asyncio
    async def test_create_experiment(self, ab_manager, version_manager):
        """Test creating A/B experiment"""
        workflow_id = "test-workflow-ab-1"

        # Create workflow versions
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={"model": "claude"},
            author="test",
            changelog="v1",
        )

        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={"model": "gpt4"},
            author="test",
            changelog="v2",
            set_active=False,
        )

        # Create experiment
        experiment = await ab_manager.create_experiment(
            workflow_id=workflow_id,
            name="Model Comparison",
            description="Test different models",
            variants=[
                Variant(
                    variant_id="control",
                    workflow_version="1.0.0",
                    traffic_weight=0.5,
                    description="Claude",
                ),
                Variant(
                    variant_id="test",
                    workflow_version="2.0.0",
                    traffic_weight=0.5,
                    description="GPT-4",
                ),
            ],
        )

        assert experiment.experiment_id is not None
        assert experiment.status == ExperimentStatus.DRAFT
        assert len(experiment.variants) == 2

    @pytest.mark.asyncio
    async def test_start_experiment(self, ab_manager, version_manager):
        """Test starting experiment"""
        workflow_id = "test-workflow-ab-2"

        # Create versions
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={},
            author="test",
            changelog="v1",
        )

        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={},
            author="test",
            changelog="v2",
            set_active=False,
        )

        # Create experiment
        experiment = await ab_manager.create_experiment(
            workflow_id=workflow_id,
            name="Test",
            description="Test",
            variants=[
                Variant("control", "1.0.0", 0.5, "control"),
                Variant("test", "2.0.0", 0.5, "test"),
            ],
        )

        # Start
        await ab_manager.start_experiment(experiment.experiment_id)

        # Verify status
        updated = await ab_manager.get_experiment(experiment.experiment_id)
        assert updated.status == ExperimentStatus.RUNNING
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_assign_variant(self, ab_manager, version_manager):
        """Test variant assignment (traffic splitting)"""
        workflow_id = "test-workflow-ab-3"

        # Create versions
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={},
            author="test",
            changelog="v1",
        )

        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={},
            author="test",
            changelog="v2",
            set_active=False,
        )

        # Create and start experiment
        experiment = await ab_manager.create_experiment(
            workflow_id=workflow_id,
            name="Test",
            description="Test",
            variants=[
                Variant("control", "1.0.0", 0.5, "control"),
                Variant("test", "2.0.0", 0.5, "test"),
            ],
        )

        await ab_manager.start_experiment(experiment.experiment_id)

        # Assign variant
        variant = await ab_manager.assign_variant(
            experiment.experiment_id, user_id="user123"
        )

        assert variant is not None
        assert variant.variant_id in ["control", "test"]

        # Sticky assignment (same user gets same variant)
        variant2 = await ab_manager.assign_variant(
            experiment.experiment_id, user_id="user123", sticky=True
        )

        assert variant.variant_id == variant2.variant_id

    @pytest.mark.asyncio
    async def test_record_metrics(self, ab_manager, version_manager):
        """Test recording metrics"""
        workflow_id = "test-workflow-ab-4"

        # Setup
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={},
            author="test",
            changelog="v1",
        )

        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={},
            author="test",
            changelog="v2",
            set_active=False,
        )

        experiment = await ab_manager.create_experiment(
            workflow_id=workflow_id,
            name="Test",
            description="Test",
            variants=[
                Variant("control", "1.0.0", 0.5, "control"),
                Variant("test", "2.0.0", 0.5, "test"),
            ],
        )

        await ab_manager.start_experiment(experiment.experiment_id)

        # Record metrics
        await ab_manager.record_impression(experiment.experiment_id, "control")
        await ab_manager.record_success(
            experiment.experiment_id, "control", latency=1.5, cost=0.05
        )

        # Get metrics
        metrics = await ab_manager.get_metrics(experiment.experiment_id)

        assert "control" in metrics
        assert metrics["control"].impressions == 1
        assert metrics["control"].successes == 1
        assert metrics["control"].total_latency == 1.5
        assert metrics["control"].total_cost == 0.05
        assert metrics["control"].conversion_rate == 1.0

    @pytest.mark.asyncio
    async def test_check_winner(self, ab_manager, version_manager):
        """Test checking for statistical winner"""
        workflow_id = "test-workflow-ab-5"

        # Setup
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={},
            author="test",
            changelog="v1",
        )

        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={},
            author="test",
            changelog="v2",
            set_active=False,
        )

        experiment = await ab_manager.create_experiment(
            workflow_id=workflow_id,
            name="Test",
            description="Test",
            variants=[
                Variant("control", "1.0.0", 0.5, "control"),
                Variant("test", "2.0.0", 0.5, "test"),
            ],
            min_sample_size=10,
        )

        await ab_manager.start_experiment(experiment.experiment_id)

        # Simulate traffic (100 impressions each)
        for i in range(100):
            # Control: 70% success
            await ab_manager.record_impression(experiment.experiment_id, "control")
            if i < 70:
                await ab_manager.record_success(experiment.experiment_id, "control")

            # Test: 80% success
            await ab_manager.record_impression(experiment.experiment_id, "test")
            if i < 80:
                await ab_manager.record_success(experiment.experiment_id, "test")

        # Check winner
        test_result = await ab_manager.check_winner(experiment.experiment_id)

        assert test_result is not None
        assert test_result.winner in ["control", "test"]

    @pytest.mark.asyncio
    async def test_list_experiments(self, ab_manager, version_manager):
        """Test listing experiments"""
        workflow_id = "test-workflow-ab-6"

        # Create versions
        await version_manager.create_version(
            workflow_id=workflow_id,
            version="1.0.0",
            workflow_data={},
            author="test",
            changelog="v1",
        )

        await version_manager.create_version(
            workflow_id=workflow_id,
            version="2.0.0",
            workflow_data={},
            author="test",
            changelog="v2",
            set_active=False,
        )

        # Create 2 experiments
        for i in range(2):
            await ab_manager.create_experiment(
                workflow_id=workflow_id,
                name=f"Experiment {i}",
                description="Test",
                variants=[
                    Variant("control", "1.0.0", 0.5, "control"),
                    Variant("test", "2.0.0", 0.5, "test"),
                ],
            )

        # List experiments
        experiments = await ab_manager.list_experiments(workflow_id)

        assert len(experiments) == 2
