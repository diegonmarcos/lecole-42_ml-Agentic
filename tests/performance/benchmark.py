"""
Performance Benchmarks - TASK-042

Benchmarks for LLM operations, RAG, and multi-agent workflows:
- Throughput (requests/second)
- Latency (P50, P95, P99)
- Cost efficiency ($/request)
- Resource usage (CPU, memory)
- Concurrent request handling
"""

import asyncio
import time
import statistics
import json
import psutil
from typing import List, Dict, Any, Callable
from dataclasses import dataclass


@dataclass
class BenchmarkResult:
    """Benchmark result metrics"""

    name: str
    total_requests: int
    duration: float  # seconds
    throughput: float  # requests/second
    latencies: List[float]  # All latency measurements
    p50_latency: float
    p95_latency: float
    p99_latency: float
    min_latency: float
    max_latency: float
    avg_latency: float
    success_count: int
    failure_count: int
    success_rate: float
    total_cost: float = 0.0
    cost_per_request: float = 0.0
    cpu_usage: float = 0.0  # Average CPU %
    memory_usage: float = 0.0  # Average memory MB


class PerformanceBenchmark:
    """
    Performance benchmark runner.

    Usage:
        benchmark = PerformanceBenchmark()

        # Benchmark single function
        result = await benchmark.run(
            name="LLM Chat Completion",
            func=lambda: provider.chat_completion(...),
            iterations=100,
            concurrency=10
        )

        # Benchmark workflow
        result = await benchmark.run_workflow(
            name="Plan-Code-Review",
            workflow_func=run_workflow,
            iterations=50
        )

        # Generate report
        benchmark.print_report(result)
    """

    def __init__(self):
        self.process = psutil.Process()
        self.results: List[BenchmarkResult] = []

    async def run(
        self,
        name: str,
        func: Callable,
        iterations: int = 100,
        concurrency: int = 1,
        warmup: int = 5,
        track_cost: bool = False,
    ) -> BenchmarkResult:
        """
        Run benchmark for a function.

        Args:
            name: Benchmark name
            func: Async function to benchmark
            iterations: Number of iterations
            concurrency: Concurrent executions
            warmup: Warmup iterations (excluded from results)
            track_cost: Track cost metrics

        Returns:
            BenchmarkResult with metrics
        """
        print(f"\n🏃 Running benchmark: {name}")
        print(f"   Iterations: {iterations}, Concurrency: {concurrency}")

        # Warmup
        if warmup > 0:
            print(f"   Warming up ({warmup} iterations)...")
            for _ in range(warmup):
                try:
                    if asyncio.iscoroutinefunction(func):
                        await func()
                    else:
                        func()
                except Exception:
                    pass

        # Benchmark
        latencies = []
        success_count = 0
        failure_count = 0
        total_cost = 0.0
        cpu_measurements = []
        memory_measurements = []

        print("   Benchmarking...")
        start_time = time.time()

        # Run in batches based on concurrency
        for batch_start in range(0, iterations, concurrency):
            batch_size = min(concurrency, iterations - batch_start)

            # Record resource usage before batch
            cpu_measurements.append(self.process.cpu_percent())
            memory_measurements.append(
                self.process.memory_info().rss / 1024 / 1024
            )  # MB

            # Create tasks for concurrent execution
            tasks = []
            for _ in range(batch_size):
                if asyncio.iscoroutinefunction(func):
                    tasks.append(self._measure_async(func))
                else:
                    tasks.append(self._measure_sync(func))

            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    failure_count += 1
                elif isinstance(result, dict):
                    latencies.append(result["latency"])
                    success_count += 1
                    if track_cost and "cost" in result:
                        total_cost += result["cost"]

        duration = time.time() - start_time

        # Calculate metrics
        if not latencies:
            raise ValueError("No successful iterations to benchmark")

        latencies.sort()
        p50_idx = int(len(latencies) * 0.50)
        p95_idx = int(len(latencies) * 0.95)
        p99_idx = int(len(latencies) * 0.99)

        result = BenchmarkResult(
            name=name,
            total_requests=iterations,
            duration=duration,
            throughput=iterations / duration,
            latencies=latencies,
            p50_latency=latencies[p50_idx],
            p95_latency=latencies[p95_idx],
            p99_latency=latencies[p99_idx],
            min_latency=min(latencies),
            max_latency=max(latencies),
            avg_latency=statistics.mean(latencies),
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_count / iterations,
            total_cost=total_cost,
            cost_per_request=total_cost / success_count if success_count > 0 else 0.0,
            cpu_usage=statistics.mean(cpu_measurements) if cpu_measurements else 0.0,
            memory_usage=statistics.mean(memory_measurements)
            if memory_measurements
            else 0.0,
        )

        self.results.append(result)

        print("   ✓ Complete")

        return result

    async def _measure_async(self, func: Callable) -> Dict[str, Any]:
        """Measure async function execution"""
        start = time.time()
        try:
            result = await func()
            latency = time.time() - start

            # Try to extract cost if result is a dict
            cost = 0.0
            if isinstance(result, dict) and "cost" in result:
                cost = result["cost"]

            return {"latency": latency, "cost": cost}

        except Exception as e:
            raise e

    async def _measure_sync(self, func: Callable) -> Dict[str, Any]:
        """Measure sync function execution"""
        start = time.time()
        try:
            result = func()
            latency = time.time() - start

            cost = 0.0
            if isinstance(result, dict) and "cost" in result:
                cost = result["cost"]

            return {"latency": latency, "cost": cost}

        except Exception as e:
            raise e

    def print_report(self, result: BenchmarkResult):
        """Print formatted benchmark report"""
        print(f"\n{'='*70}")
        print(f"  📊 Benchmark Report: {result.name}")
        print(f"{'='*70}")

        print("\n  Throughput:")
        print(f"    {result.throughput:.2f} requests/second")

        print("\n  Latency:")
        print(f"    P50: {result.p50_latency*1000:.2f}ms")
        print(f"    P95: {result.p95_latency*1000:.2f}ms")
        print(f"    P99: {result.p99_latency*1000:.2f}ms")
        print(f"    Avg: {result.avg_latency*1000:.2f}ms")
        print(f"    Min: {result.min_latency*1000:.2f}ms")
        print(f"    Max: {result.max_latency*1000:.2f}ms")

        print("\n  Reliability:")
        print(f"    Success rate: {result.success_rate:.1%}")
        print(f"    Successes: {result.success_count}")
        print(f"    Failures: {result.failure_count}")

        if result.total_cost > 0:
            print("\n  Cost:")
            print(f"    Total: ${result.total_cost:.4f}")
            print(f"    Per request: ${result.cost_per_request:.6f}")

        print("\n  Resources:")
        print(f"    Avg CPU: {result.cpu_usage:.1f}%")
        print(f"    Avg Memory: {result.memory_usage:.1f}MB")

        print(f"\n  Duration: {result.duration:.2f}s")
        print(f"{'='*70}\n")

    def print_comparison(self, results: List[BenchmarkResult]):
        """Print comparison table of multiple benchmarks"""
        print(f"\n{'='*120}")
        print("  📈 Benchmark Comparison")
        print(f"{'='*120}")

        # Header
        print(
            f"  {'Benchmark':<40} {'Throughput':>12} {'P95 Latency':>12} "
            f"{'Success Rate':>12} {'Cost/Req':>12}"
        )
        print(f"  {'-'*40} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")

        # Rows
        for result in results:
            print(
                f"  {result.name:<40} "
                f"{result.throughput:>10.2f}/s "
                f"{result.p95_latency*1000:>10.2f}ms "
                f"{result.success_rate:>11.1%} "
                f"${result.cost_per_request:>11.6f}"
            )

        print(f"{'='*120}\n")

    def export_json(self, filepath: str):
        """Export results to JSON"""
        data = []
        for result in self.results:
            data.append(
                {
                    "name": result.name,
                    "total_requests": result.total_requests,
                    "duration": result.duration,
                    "throughput": result.throughput,
                    "latency": {
                        "p50": result.p50_latency,
                        "p95": result.p95_latency,
                        "p99": result.p99_latency,
                        "avg": result.avg_latency,
                        "min": result.min_latency,
                        "max": result.max_latency,
                    },
                    "success_rate": result.success_rate,
                    "cost_per_request": result.cost_per_request,
                    "cpu_usage": result.cpu_usage,
                    "memory_usage": result.memory_usage,
                }
            )

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        print(f"✓ Exported results to {filepath}")


# Example benchmarks
if __name__ == "__main__":

    async def main():
        benchmark = PerformanceBenchmark()

        # 1. Benchmark simple computation
        print("\n" + "=" * 70)
        print("  SIMPLE COMPUTATION BENCHMARK")
        print("=" * 70)

        async def simple_task():
            await asyncio.sleep(0.01)  # Simulate work
            return sum(range(1000))

        result1 = await benchmark.run(
            name="Simple Computation", func=simple_task, iterations=100, concurrency=10
        )

        benchmark.print_report(result1)

        # 2. Benchmark I/O operation
        print("\n" + "=" * 70)
        print("  I/O OPERATION BENCHMARK")
        print("=" * 70)

        async def io_task():
            await asyncio.sleep(0.05)  # Simulate I/O
            return {"data": "result"}

        result2 = await benchmark.run(
            name="I/O Operation", func=io_task, iterations=100, concurrency=20
        )

        benchmark.print_report(result2)

        # 3. Benchmark with cost tracking
        print("\n" + "=" * 70)
        print("  COST TRACKING BENCHMARK")
        print("=" * 70)

        async def cost_task():
            await asyncio.sleep(0.02)
            return {"result": "data", "cost": 0.001}

        result3 = await benchmark.run(
            name="Task with Cost",
            func=cost_task,
            iterations=100,
            concurrency=10,
            track_cost=True,
        )

        benchmark.print_report(result3)

        # Print comparison
        benchmark.print_comparison([result1, result2, result3])

        # Export results
        benchmark.export_json("benchmark_results.json")

    asyncio.run(main())
