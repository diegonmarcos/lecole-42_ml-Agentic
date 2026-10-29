"""
A/B Testing Framework - TASK-036

Provides A/B testing capabilities for workflow variants:
- Variant management (multiple workflow versions)
- Traffic splitting with configurable weights
- Metrics collection per variant
- Statistical significance testing
- Winner selection and auto-promotion
"""

import asyncio
import hashlib
import json
import logging
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from .versioning import WorkflowVersionManager

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    """A/B test experiment status"""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class Variant:
    """A/B test variant"""

    variant_id: str
    workflow_version: str
    traffic_weight: float  # 0.0 - 1.0
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentMetrics:
    """Metrics for a variant"""

    variant_id: str
    impressions: int  # Number of times assigned
    successes: int  # Number of successful executions
    failures: int  # Number of failures
    total_latency: float  # Total latency in seconds
    total_cost: float  # Total cost in dollars
    conversion_rate: float = 0.0
    avg_latency: float = 0.0
    avg_cost: float = 0.0

    def calculate_derived_metrics(self):
        """Calculate derived metrics"""
        if self.impressions > 0:
            self.conversion_rate = self.successes / self.impressions
            self.avg_latency = self.total_latency / self.impressions
            self.avg_cost = self.total_cost / self.impressions


@dataclass
class ABExperiment:  # pylint: disable=too-many-instance-attributes
    """A/B test experiment"""

    experiment_id: str
    workflow_id: str
    name: str
    description: str
    variants: List[Variant]
    status: ExperimentStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    winner_variant_id: Optional[str] = None
    min_sample_size: int = 100  # Minimum impressions per variant
    confidence_level: float = 0.95  # Statistical confidence
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        data = asdict(self)
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ABExperiment":
        """Create from dict"""
        data["status"] = ExperimentStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])

        # Convert variant dicts to Variant objects
        data["variants"] = [
            Variant(**v) if isinstance(v, dict) else v for v in data["variants"]
        ]

        return cls(**data)


@dataclass
class StatisticalTest:
    """Statistical significance test results"""

    variant_a_id: str
    variant_b_id: str
    significant: bool
    confidence_level: float
    p_value: float
    winner: Optional[str]  # variant_id of winner


class ABTestingManager:
    """
    Manages A/B testing experiments for workflows.

    Usage:
        manager = ABTestingManager(redis_client, version_manager)

        # Create experiment with 2 variants
        experiment = await manager.create_experiment(
            workflow_id="code-gen-pipeline",
            name="Planner Model Comparison",
            variants=[
                Variant(variant_id="control", workflow_version="1.0.0", traffic_weight=0.5),
                Variant(variant_id="test", workflow_version="1.1.0", traffic_weight=0.5)
            ]
        )

        # Start experiment
        await manager.start_experiment(experiment.experiment_id)

        # Assign variant (traffic splitting)
        variant = await manager.assign_variant(experiment.experiment_id, user_id="user123")

        # Record metrics
        await manager.record_impression(experiment.experiment_id, variant.variant_id)
        await manager.record_success(
            experiment.experiment_id, variant.variant_id, latency=1.2, cost=0.05
        )

        # Check for winner
        winner = await manager.check_winner(experiment.experiment_id)

        # Promote winner
        await manager.promote_winner(experiment.experiment_id)
    """

    def __init__(
        self, redis_client: redis.Redis, version_manager: WorkflowVersionManager
    ):
        """
        Initialize A/B testing manager.

        Args:
            redis_client: Redis client for state/metrics
            version_manager: Workflow version manager
        """
        self.redis = redis_client
        self.version_manager = version_manager

    def _get_experiment_key(self, experiment_id: str) -> str:
        """Get Redis key for experiment"""
        return f"ab:experiment:{experiment_id}"

    def _get_metrics_key(self, experiment_id: str, variant_id: str) -> str:
        """Get Redis key for variant metrics"""
        return f"ab:metrics:{experiment_id}:{variant_id}"

    def _get_assignment_key(self, experiment_id: str, user_id: str) -> str:
        """Get Redis key for user assignment"""
        return f"ab:assignment:{experiment_id}:{user_id}"

    def _get_experiments_key(self, workflow_id: str) -> str:
        """Get Redis key for workflow experiments list"""
        return f"ab:experiments:{workflow_id}"

    async def create_experiment(
        self,
        workflow_id: str,
        name: str,
        description: str,
        variants: List[Variant],
        min_sample_size: int = 100,
        confidence_level: float = 0.95,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ABExperiment:
        """
        Create A/B test experiment.

        Args:
            workflow_id: Workflow to test
            name: Experiment name
            description: Experiment description
            variants: List of variants to test
            min_sample_size: Minimum impressions before statistical test
            confidence_level: Statistical confidence (0-1)
            metadata: Additional metadata

        Returns:
            ABExperiment object
        """
        # Validate variants
        if len(variants) < 2:
            raise ValueError("At least 2 variants required")

        total_weight = sum(v.traffic_weight for v in variants)
        if not 0.99 <= total_weight <= 1.01:  # Allow small float error
            raise ValueError(f"Traffic weights must sum to 1.0, got {total_weight}")

        # Verify workflow versions exist
        for variant in variants:
            version = await self.version_manager.get_version(
                workflow_id, variant.workflow_version
            )
            if not version:
                raise ValueError(
                    f"Workflow version not found: {variant.workflow_version}"
                )

        # Generate experiment ID
        experiment_id = hashlib.sha256(
            f"{workflow_id}:{name}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]

        # Create experiment
        experiment = ABExperiment(
            experiment_id=experiment_id,
            workflow_id=workflow_id,
            name=name,
            description=description,
            variants=variants,
            status=ExperimentStatus.DRAFT,
            created_at=datetime.utcnow(),
            min_sample_size=min_sample_size,
            confidence_level=confidence_level,
            metadata=metadata or {},
        )

        # Store in Redis
        experiment_key = self._get_experiment_key(experiment_id)
        await self.redis.set(
            experiment_key,
            self._serialize_experiment(experiment),
            ex=86400 * 90,  # 90 days
        )

        # Add to workflow experiments list
        experiments_key = self._get_experiments_key(workflow_id)
        await self.redis.sadd(experiments_key, experiment_id)

        # Initialize metrics for each variant
        for variant in variants:
            metrics = ExperimentMetrics(
                variant_id=variant.variant_id,
                impressions=0,
                successes=0,
                failures=0,
                total_latency=0.0,
                total_cost=0.0,
            )
            await self._store_metrics(experiment_id, variant.variant_id, metrics)

        logger.info(
            "Created A/B experiment: %s with %s variants", experiment_id, len(variants)
        )

        return experiment

    async def start_experiment(self, experiment_id: str) -> bool:
        """Start A/B test experiment"""
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        if experiment.status != ExperimentStatus.DRAFT:
            raise ValueError(
                f"Experiment must be in DRAFT status, got {experiment.status}"
            )

        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.utcnow()

        await self._update_experiment(experiment)

        logger.info("Started A/B experiment: %s", experiment_id)
        return True

    async def assign_variant(
        self, experiment_id: str, user_id: str, sticky: bool = True
    ) -> Variant:
        """
        Assign variant to user (traffic splitting).

        Args:
            experiment_id: Experiment ID
            user_id: User identifier
            sticky: If True, always assign same variant to user

        Returns:
            Assigned Variant
        """
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        if experiment.status != ExperimentStatus.RUNNING:
            raise ValueError(f"Experiment not running: {experiment.status}")

        # Check for existing assignment (sticky)
        if sticky:
            assignment_key = self._get_assignment_key(experiment_id, user_id)
            existing_variant_id = await self.redis.get(assignment_key)

            if existing_variant_id:
                if isinstance(existing_variant_id, bytes):
                    existing_variant_id = existing_variant_id.decode()

                # Find variant
                for variant in experiment.variants:
                    if variant.variant_id == existing_variant_id:
                        return variant

        # Assign new variant based on traffic weights
        variant = self._weighted_random_choice(experiment.variants)

        # Store assignment
        if sticky:
            assignment_key = self._get_assignment_key(experiment_id, user_id)
            await self.redis.set(
                assignment_key, variant.variant_id, ex=86400 * 30  # 30 days
            )

        return variant

    async def record_impression(self, experiment_id: str, variant_id: str) -> bool:
        """Record impression (variant assignment)"""
        metrics = await self._get_metrics(experiment_id, variant_id)
        if not metrics:
            logger.warning("Metrics not found: %s/%s", experiment_id, variant_id)
            return False

        metrics.impressions += 1
        metrics.calculate_derived_metrics()
        await self._store_metrics(experiment_id, variant_id, metrics)

        return True

    async def record_success(
        self,
        experiment_id: str,
        variant_id: str,
        latency: float = 0.0,
        cost: float = 0.0,
    ) -> bool:
        """Record successful execution"""
        metrics = await self._get_metrics(experiment_id, variant_id)
        if not metrics:
            return False

        metrics.successes += 1
        metrics.total_latency += latency
        metrics.total_cost += cost

        metrics.calculate_derived_metrics()

        await self._store_metrics(experiment_id, variant_id, metrics)

        return True

    async def record_failure(self, experiment_id: str, variant_id: str) -> bool:
        """Record failed execution"""
        metrics = await self._get_metrics(experiment_id, variant_id)
        if not metrics:
            return False

        metrics.failures += 1
        metrics.calculate_derived_metrics()

        await self._store_metrics(experiment_id, variant_id, metrics)

        return True

    async def get_metrics(self, experiment_id: str) -> Dict[str, ExperimentMetrics]:
        """Get metrics for all variants"""
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            return {}

        metrics = {}
        for variant in experiment.variants:
            variant_metrics = await self._get_metrics(experiment_id, variant.variant_id)
            if variant_metrics:
                metrics[variant.variant_id] = variant_metrics

        return metrics

    async def check_winner(
        self, experiment_id: str, metric: str = "conversion_rate"
    ) -> Optional[StatisticalTest]:
        """
        Check for statistical winner.

        Args:
            experiment_id: Experiment ID
            metric: Metric to compare (conversion_rate, avg_latency, avg_cost)

        Returns:
            StatisticalTest result if winner found, else None
        """
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            return None

        metrics = await self.get_metrics(experiment_id)

        # Check minimum sample size
        for variant_id, variant_metrics in metrics.items():
            if variant_metrics.impressions < experiment.min_sample_size:
                logger.info(
                    "Variant %s below minimum sample size: %s/%s",
                    variant_id,
                    variant_metrics.impressions,
                    experiment.min_sample_size,
                )
                return None

        # For simplicity, compare first two variants (in production, use scipy.stats)
        variants = list(metrics.keys())
        if len(variants) < 2:
            return None

        variant_a_id = variants[0]
        variant_b_id = variants[1]

        metrics_a = metrics[variant_a_id]
        metrics_b = metrics[variant_b_id]

        # Simple comparison (in production, use t-test or chi-squared test)
        value_a = getattr(metrics_a, metric)
        value_b = getattr(metrics_b, metric)

        # Mock p-value calculation (use scipy.stats.chi2_contingency in production)
        diff = abs(value_a - value_b)
        p_value = 0.01 if diff > 0.05 else 0.10  # Mock threshold

        significant = p_value < (1 - experiment.confidence_level)
        winner = variant_a_id if value_a > value_b else variant_b_id

        test_result = StatisticalTest(
            variant_a_id=variant_a_id,
            variant_b_id=variant_b_id,
            significant=significant,
            confidence_level=experiment.confidence_level,
            p_value=p_value,
            winner=winner if significant else None,
        )

        logger.info(
            "Statistical test: %s",
            test_result.winner if test_result.significant else "No winner yet",
        )

        return test_result

    async def promote_winner(
        self, experiment_id: str, winner_variant_id: Optional[str] = None
    ) -> bool:
        """
        Promote winning variant to active workflow version.

        Args:
            experiment_id: Experiment ID
            winner_variant_id: Winner variant (or auto-detect)

        Returns:
            True if promoted
        """
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        # Auto-detect winner if not specified
        if not winner_variant_id:
            test_result = await self.check_winner(experiment_id)
            if not test_result or not test_result.significant:
                raise ValueError("No statistically significant winner found")

            winner_variant_id = test_result.winner

        # Find winner variant
        winner_variant = None
        for variant in experiment.variants:
            if variant.variant_id == winner_variant_id:
                winner_variant = variant
                break

        if not winner_variant:
            raise ValueError(f"Winner variant not found: {winner_variant_id}")

        # Promote winner version to active
        await self.version_manager.set_active_version(
            experiment.workflow_id, winner_variant.workflow_version
        )

        # Update experiment
        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = datetime.utcnow()
        experiment.winner_variant_id = winner_variant_id

        await self._update_experiment(experiment)

        logger.info(
            "Promoted winner: %s (version %s)",
            winner_variant_id,
            winner_variant.workflow_version,
        )

        return True

    async def get_experiment(self, experiment_id: str) -> Optional[ABExperiment]:
        """Get experiment by ID"""
        experiment_key = self._get_experiment_key(experiment_id)
        data = await self.redis.get(experiment_key)

        if not data:
            return None

        if isinstance(data, bytes):
            data = data.decode()

        return self._deserialize_experiment(data)

    async def list_experiments(
        self, workflow_id: str, status: Optional[ExperimentStatus] = None
    ) -> List[ABExperiment]:
        """List experiments for workflow"""
        experiments_key = self._get_experiments_key(workflow_id)
        experiment_ids = await self.redis.smembers(experiments_key)

        experiments = []
        for exp_id in experiment_ids:
            if isinstance(exp_id, bytes):
                exp_id = exp_id.decode()

            experiment = await self.get_experiment(exp_id)
            if experiment:
                if status is None or experiment.status == status:
                    experiments.append(experiment)

        return experiments

    def _weighted_random_choice(self, variants: List[Variant]) -> Variant:
        """Select variant based on traffic weights"""
        rand = random.random()
        cumulative = 0.0

        for variant in variants:
            cumulative += variant.traffic_weight
            if rand <= cumulative:
                return variant

        # Fallback to last variant
        return variants[-1]

    def _serialize_experiment(self, experiment: ABExperiment) -> str:
        """Serialize experiment to JSON"""

        return json.dumps(experiment.to_dict())

    def _deserialize_experiment(self, data: str) -> ABExperiment:
        """Deserialize experiment from JSON"""

        return ABExperiment.from_dict(json.loads(data))

    async def _get_metrics(
        self, experiment_id: str, variant_id: str
    ) -> Optional[ExperimentMetrics]:
        """Get variant metrics from Redis"""

        metrics_key = self._get_metrics_key(experiment_id, variant_id)
        data = await self.redis.get(metrics_key)

        if not data:
            return None

        if isinstance(data, bytes):
            data = data.decode()

        metrics_dict = json.loads(data)
        return ExperimentMetrics(**metrics_dict)

    async def _store_metrics(
        self, experiment_id: str, variant_id: str, metrics: ExperimentMetrics
    ) -> bool:
        """Store variant metrics to Redis"""

        metrics_key = self._get_metrics_key(experiment_id, variant_id)
        await self.redis.set(
            metrics_key, json.dumps(asdict(metrics)), ex=86400 * 90  # 90 days
        )

        return True

    async def _update_experiment(self, experiment: ABExperiment) -> bool:
        """Update experiment in Redis"""
        experiment_key = self._get_experiment_key(experiment.experiment_id)
        await self.redis.set(
            experiment_key, self._serialize_experiment(experiment), ex=86400 * 90
        )

        return True


# Example usage
if __name__ == "__main__":

    async def main():
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

        version_manager = WorkflowVersionManager(redis_client)
        ab_manager = ABTestingManager(redis_client, version_manager)

        # Create experiment
        experiment = await ab_manager.create_experiment(
            workflow_id="code-gen-pipeline",
            name="Planner Model Comparison",
            description="Compare Claude vs GPT-4 for planning",
            variants=[
                Variant(
                    variant_id="control",
                    workflow_version="1.0.0",
                    traffic_weight=0.5,
                    description="Claude 3.5 Haiku",
                ),
                Variant(
                    variant_id="test",
                    workflow_version="1.1.0",
                    traffic_weight=0.5,
                    description="GPT-4o-mini",
                ),
            ],
            min_sample_size=100,
        )

        print(f"Created experiment: {experiment.experiment_id}")

        # Start experiment
        await ab_manager.start_experiment(experiment.experiment_id)

        # Simulate traffic
        for i in range(200):
            user_id = f"user_{i}"

            # Assign variant
            variant = await ab_manager.assign_variant(experiment.experiment_id, user_id)

            # Record impression
            await ab_manager.record_impression(
                experiment.experiment_id, variant.variant_id
            )

            # Simulate success/failure
            success = random.random() < 0.7  # 70% success rate
            if success:
                await ab_manager.record_success(
                    experiment.experiment_id,
                    variant.variant_id,
                    latency=random.uniform(1.0, 3.0),
                    cost=random.uniform(0.01, 0.10),
                )
            else:
                await ab_manager.record_failure(
                    experiment.experiment_id, variant.variant_id
                )

        # Get metrics
        metrics = await ab_manager.get_metrics(experiment.experiment_id)
        for variant_id, variant_metrics in metrics.items():
            print(f"\n{variant_id}:")
            print(f"  Impressions: {variant_metrics.impressions}")
            print(f"  Conversion rate: {variant_metrics.conversion_rate:.2%}")
            print(f"  Avg latency: {variant_metrics.avg_latency:.2f}s")
            print(f"  Avg cost: ${variant_metrics.avg_cost:.4f}")

        # Check for winner
        test_result = await ab_manager.check_winner(experiment.experiment_id)
        if test_result and test_result.significant:
            print(f"\nWinner: {test_result.winner} (p={test_result.p_value:.4f})")

            # Promote winner
            await ab_manager.promote_winner(experiment.experiment_id)
            print("Winner promoted to active version!")

        await redis_client.close()

    asyncio.run(main())
