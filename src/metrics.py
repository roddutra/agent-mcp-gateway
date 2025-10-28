"""Metrics collection for Agent MCP Gateway."""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class OperationMetrics:
    """Metrics for a specific operation.

    Attributes:
        count: Total number of operations recorded
        total_latency_ms: Cumulative latency in milliseconds
        latencies: List of individual latency measurements
        errors: Number of operations that resulted in errors
    """
    count: int = 0
    total_latency_ms: float = 0.0
    latencies: List[float] = field(default_factory=list)
    errors: int = 0

    def record(self, latency_ms: float, is_error: bool = False):
        """Record a single operation.

        Args:
            latency_ms: Operation latency in milliseconds
            is_error: Whether the operation resulted in an error
        """
        self.count += 1
        self.total_latency_ms += latency_ms
        self.latencies.append(latency_ms)
        if is_error:
            self.errors += 1

    def get_summary(self) -> dict:
        """Generate summary statistics for this operation.

        Returns:
            Dictionary containing count, avg, percentiles, and error_rate
        """
        if self.count == 0:
            return {
                "count": 0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
                "error_rate": 0.0
            }

        avg_latency = self.total_latency_ms / self.count
        error_rate = self.errors / self.count

        # Calculate percentiles
        sorted_latencies = sorted(self.latencies)
        p50 = self._percentile(sorted_latencies, 50)
        p95 = self._percentile(sorted_latencies, 95)
        p99 = self._percentile(sorted_latencies, 99)

        return {
            "count": self.count,
            "avg_latency_ms": round(avg_latency, 2),
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "p99_latency_ms": round(p99, 2),
            "error_rate": round(error_rate, 4)
        }

    @staticmethod
    def _percentile(sorted_values: List[float], percentile: int) -> float:
        """Calculate percentile from sorted values.

        Args:
            sorted_values: List of values sorted in ascending order
            percentile: Percentile to calculate (0-100)

        Returns:
            Value at the specified percentile
        """
        if not sorted_values:
            return 0.0

        if len(sorted_values) == 1:
            return sorted_values[0]

        # Use linear interpolation method
        k = (len(sorted_values) - 1) * (percentile / 100.0)
        f = int(k)
        c = f + 1

        if c >= len(sorted_values):
            return sorted_values[-1]

        # Interpolate between floor and ceiling
        d0 = sorted_values[f] * (c - k)
        d1 = sorted_values[c] * (k - f)

        return d0 + d1


class MetricsCollector:
    """Collects and aggregates metrics for gateway operations.

    Thread-safe metrics collection with per-agent and per-operation tracking.
    Metrics are stored in memory and can be aggregated for monitoring.
    """

    def __init__(self):
        """Initialize metrics collector with empty storage."""
        # Overall metrics: operation -> OperationMetrics
        self._metrics: Dict[str, OperationMetrics] = {}

        # Per-agent metrics: agent_id -> operation -> OperationMetrics
        self._agent_metrics: Dict[str, Dict[str, OperationMetrics]] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def record(
        self,
        agent_id: str,
        operation: str,
        latency_ms: float,
        is_error: bool = False
    ):
        """Record a single operation metric.

        Args:
            agent_id: Agent identifier
            operation: Operation name (list_servers, execute_tool, etc.)
            latency_ms: Operation latency in milliseconds
            is_error: Whether the operation resulted in an error
        """
        async with self._lock:
            # Record overall metrics
            if operation not in self._metrics:
                self._metrics[operation] = OperationMetrics()
            self._metrics[operation].record(latency_ms, is_error)

            # Record per-agent metrics
            if agent_id not in self._agent_metrics:
                self._agent_metrics[agent_id] = {}
            if operation not in self._agent_metrics[agent_id]:
                self._agent_metrics[agent_id][operation] = OperationMetrics()
            self._agent_metrics[agent_id][operation].record(latency_ms, is_error)

    def record_sync(
        self,
        agent_id: str,
        operation: str,
        latency_ms: float,
        is_error: bool = False
    ):
        """Record a single operation metric (synchronous version).

        Note: This is not thread-safe. Use async record() for concurrent access.

        Args:
            agent_id: Agent identifier
            operation: Operation name (list_servers, execute_tool, etc.)
            latency_ms: Operation latency in milliseconds
            is_error: Whether the operation resulted in an error
        """
        # Record overall metrics
        if operation not in self._metrics:
            self._metrics[operation] = OperationMetrics()
        self._metrics[operation].record(latency_ms, is_error)

        # Record per-agent metrics
        if agent_id not in self._agent_metrics:
            self._agent_metrics[agent_id] = {}
        if operation not in self._agent_metrics[agent_id]:
            self._agent_metrics[agent_id][operation] = OperationMetrics()
        self._agent_metrics[agent_id][operation].record(latency_ms, is_error)

    async def get_summary(self) -> dict:
        """Get overall summary of all operations.

        Returns:
            Dictionary mapping operation names to their summary statistics
        """
        async with self._lock:
            return self._get_summary_internal()

    def get_summary_sync(self) -> dict:
        """Get overall summary of all operations (synchronous version).

        Returns:
            Dictionary mapping operation names to their summary statistics
        """
        return self._get_summary_internal()

    def _get_summary_internal(self) -> dict:
        """Internal method to get summary without locking."""
        return {
            operation: metrics.get_summary()
            for operation, metrics in self._metrics.items()
        }

    async def get_agent_summary(self, agent_id: str) -> dict:
        """Get summary for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary mapping operation names to summary statistics for this agent,
            or empty dict if agent has no recorded metrics
        """
        async with self._lock:
            return self._get_agent_summary_internal(agent_id)

    def get_agent_summary_sync(self, agent_id: str) -> dict:
        """Get summary for a specific agent (synchronous version).

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary mapping operation names to summary statistics for this agent,
            or empty dict if agent has no recorded metrics
        """
        return self._get_agent_summary_internal(agent_id)

    def _get_agent_summary_internal(self, agent_id: str) -> dict:
        """Internal method to get agent summary without locking."""
        if agent_id not in self._agent_metrics:
            return {}

        return {
            operation: metrics.get_summary()
            for operation, metrics in self._agent_metrics[agent_id].items()
        }

    async def get_operation_summary(self, operation: str) -> dict:
        """Get summary for a specific operation.

        Args:
            operation: Operation name

        Returns:
            Summary statistics for this operation, or empty metrics if not found
        """
        async with self._lock:
            return self._get_operation_summary_internal(operation)

    def get_operation_summary_sync(self, operation: str) -> dict:
        """Get summary for a specific operation (synchronous version).

        Args:
            operation: Operation name

        Returns:
            Summary statistics for this operation, or empty metrics if not found
        """
        return self._get_operation_summary_internal(operation)

    def _get_operation_summary_internal(self, operation: str) -> dict:
        """Internal method to get operation summary without locking."""
        if operation not in self._metrics:
            return {
                "count": 0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
                "error_rate": 0.0
            }

        return self._metrics[operation].get_summary()

    async def get_all_agents(self) -> List[str]:
        """Get list of all agents with recorded metrics.

        Returns:
            List of agent identifiers
        """
        async with self._lock:
            return list(self._agent_metrics.keys())

    def get_all_agents_sync(self) -> List[str]:
        """Get list of all agents with recorded metrics (synchronous version).

        Returns:
            List of agent identifiers
        """
        return list(self._agent_metrics.keys())

    async def reset(self):
        """Reset all metrics (useful for testing)."""
        async with self._lock:
            self._metrics.clear()
            self._agent_metrics.clear()

    def reset_sync(self):
        """Reset all metrics (synchronous version, useful for testing)."""
        self._metrics.clear()
        self._agent_metrics.clear()
