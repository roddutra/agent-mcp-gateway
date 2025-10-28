"""Unit tests for metrics collection functionality."""

import asyncio
import pytest
from src.metrics import MetricsCollector, OperationMetrics


class TestOperationMetrics:
    """Test cases for OperationMetrics dataclass."""

    def test_operation_metrics_initialization(self):
        """Test that OperationMetrics initializes with correct defaults."""
        metrics = OperationMetrics()

        assert metrics.count == 0
        assert metrics.total_latency_ms == 0.0
        assert metrics.latencies == []
        assert metrics.errors == 0

    def test_operation_metrics_record_success(self):
        """Test recording successful operations."""
        metrics = OperationMetrics()

        metrics.record(100.0, is_error=False)
        metrics.record(200.0, is_error=False)

        assert metrics.count == 2
        assert metrics.total_latency_ms == 300.0
        assert metrics.latencies == [100.0, 200.0]
        assert metrics.errors == 0

    def test_operation_metrics_record_error(self):
        """Test recording operations with errors."""
        metrics = OperationMetrics()

        metrics.record(150.0, is_error=True)
        metrics.record(250.0, is_error=False)
        metrics.record(350.0, is_error=True)

        assert metrics.count == 3
        assert metrics.total_latency_ms == 750.0
        assert metrics.errors == 2

    def test_operation_metrics_summary_empty(self):
        """Test summary generation with no data."""
        metrics = OperationMetrics()
        summary = metrics.get_summary()

        assert summary["count"] == 0
        assert summary["avg_latency_ms"] == 0.0
        assert summary["p50_latency_ms"] == 0.0
        assert summary["p95_latency_ms"] == 0.0
        assert summary["p99_latency_ms"] == 0.0
        assert summary["error_rate"] == 0.0

    def test_operation_metrics_summary_single_value(self):
        """Test summary with a single recorded operation."""
        metrics = OperationMetrics()
        metrics.record(100.0)

        summary = metrics.get_summary()

        assert summary["count"] == 1
        assert summary["avg_latency_ms"] == 100.0
        assert summary["p50_latency_ms"] == 100.0
        assert summary["p95_latency_ms"] == 100.0
        assert summary["p99_latency_ms"] == 100.0
        assert summary["error_rate"] == 0.0

    def test_operation_metrics_summary_multiple_values(self):
        """Test summary with multiple recorded operations."""
        metrics = OperationMetrics()

        # Record operations with known distribution
        for latency in [10.0, 20.0, 30.0, 40.0, 50.0]:
            metrics.record(latency, is_error=False)

        summary = metrics.get_summary()

        assert summary["count"] == 5
        assert summary["avg_latency_ms"] == 30.0  # (10+20+30+40+50)/5
        assert summary["p50_latency_ms"] == 30.0  # Median
        assert summary["error_rate"] == 0.0

    def test_operation_metrics_error_rate_calculation(self):
        """Test error rate calculation."""
        metrics = OperationMetrics()

        # 3 success, 1 error = 25% error rate
        metrics.record(100.0, is_error=False)
        metrics.record(200.0, is_error=True)
        metrics.record(300.0, is_error=False)
        metrics.record(400.0, is_error=False)

        summary = metrics.get_summary()

        assert summary["count"] == 4
        assert metrics.errors == 1  # Check the internal errors count
        assert summary["error_rate"] == 0.25  # 1/4

    def test_percentile_calculation_odd_count(self):
        """Test percentile calculation with odd number of values."""
        metrics = OperationMetrics()

        # Values: 1, 2, 3, 4, 5, 6, 7, 8, 9
        for i in range(1, 10):
            metrics.record(float(i))

        summary = metrics.get_summary()

        # For 9 values:
        # P50 should be around 5 (median)
        # P95 should be around 9 (95th percentile)
        assert summary["p50_latency_ms"] == pytest.approx(5.0, abs=0.5)
        assert summary["p95_latency_ms"] >= 8.0

    def test_percentile_calculation_even_count(self):
        """Test percentile calculation with even number of values."""
        metrics = OperationMetrics()

        # Values: 10, 20, 30, 40, 50, 60, 70, 80, 90, 100
        for i in range(1, 11):
            metrics.record(float(i * 10))

        summary = metrics.get_summary()

        # P50 should be around 55 (between 50 and 60)
        assert summary["p50_latency_ms"] == pytest.approx(55.0, abs=5.0)
        assert summary["p95_latency_ms"] >= 95.0

    def test_percentile_calculation_large_dataset(self):
        """Test percentile calculation with large dataset."""
        metrics = OperationMetrics()

        # Record 100 values from 1 to 100
        for i in range(1, 101):
            metrics.record(float(i))

        summary = metrics.get_summary()

        # With 100 values from 1-100:
        # P50 should be around 50-51
        # P95 should be around 95-96
        # P99 should be around 99-100
        assert summary["p50_latency_ms"] == pytest.approx(50.5, abs=1.0)
        assert summary["p95_latency_ms"] == pytest.approx(95.5, abs=1.0)
        assert summary["p99_latency_ms"] == pytest.approx(99.5, abs=1.0)

    def test_summary_rounding(self):
        """Test that summary values are properly rounded."""
        metrics = OperationMetrics()

        metrics.record(10.123456)
        metrics.record(20.987654)

        summary = metrics.get_summary()

        # Should be rounded to 2 decimal places
        assert summary["avg_latency_ms"] == 15.56  # (10.123456+20.987654)/2 = 15.56


class TestMetricsCollector:
    """Test cases for MetricsCollector class."""

    def test_metrics_collector_initialization(self):
        """Test that MetricsCollector initializes correctly."""
        collector = MetricsCollector()

        summary = collector.get_summary_sync()
        assert summary == {}

    def test_metrics_record_operation(self):
        """Test recording a basic operation."""
        collector = MetricsCollector()

        collector.record_sync("agent1", "list_servers", 50.0, is_error=False)

        summary = collector.get_summary_sync()
        assert "list_servers" in summary
        assert summary["list_servers"]["count"] == 1
        assert summary["list_servers"]["avg_latency_ms"] == 50.0

    def test_metrics_per_agent_tracking(self):
        """Test that metrics are tracked per agent."""
        collector = MetricsCollector()

        # Agent1 operations
        collector.record_sync("agent1", "list_servers", 50.0)
        collector.record_sync("agent1", "execute_tool", 150.0)

        # Agent2 operations
        collector.record_sync("agent2", "list_servers", 30.0)
        collector.record_sync("agent2", "execute_tool", 200.0)

        # Check agent1 metrics
        agent1_summary = collector.get_agent_summary_sync("agent1")
        assert agent1_summary["list_servers"]["count"] == 1
        assert agent1_summary["list_servers"]["avg_latency_ms"] == 50.0
        assert agent1_summary["execute_tool"]["count"] == 1
        assert agent1_summary["execute_tool"]["avg_latency_ms"] == 150.0

        # Check agent2 metrics
        agent2_summary = collector.get_agent_summary_sync("agent2")
        assert agent2_summary["list_servers"]["count"] == 1
        assert agent2_summary["list_servers"]["avg_latency_ms"] == 30.0
        assert agent2_summary["execute_tool"]["count"] == 1
        assert agent2_summary["execute_tool"]["avg_latency_ms"] == 200.0

    def test_metrics_per_operation_tracking(self):
        """Test metrics tracking per operation across all agents."""
        collector = MetricsCollector()

        # Multiple agents calling same operation
        collector.record_sync("agent1", "execute_tool", 100.0)
        collector.record_sync("agent2", "execute_tool", 200.0)
        collector.record_sync("agent3", "execute_tool", 300.0)

        # Check overall operation metrics
        op_summary = collector.get_operation_summary_sync("execute_tool")
        assert op_summary["count"] == 3
        assert op_summary["avg_latency_ms"] == 200.0  # (100+200+300)/3

    def test_metrics_percentile_calculation(self):
        """Test accurate percentile calculation in metrics."""
        collector = MetricsCollector()

        # Record 100 operations with latencies 1-100ms
        for i in range(1, 101):
            collector.record_sync("test_agent", "test_op", float(i))

        summary = collector.get_operation_summary_sync("test_op")

        # Verify percentiles
        assert summary["count"] == 100
        assert summary["avg_latency_ms"] == 50.5
        assert summary["p50_latency_ms"] == pytest.approx(50.5, abs=1.0)
        assert summary["p95_latency_ms"] == pytest.approx(95.5, abs=1.0)
        assert summary["p99_latency_ms"] == pytest.approx(99.5, abs=1.0)

    def test_metrics_error_rate(self):
        """Test error rate calculation in metrics."""
        collector = MetricsCollector()

        # Record mix of success and errors
        collector.record_sync("agent1", "execute_tool", 100.0, is_error=False)
        collector.record_sync("agent1", "execute_tool", 150.0, is_error=True)
        collector.record_sync("agent1", "execute_tool", 120.0, is_error=False)
        collector.record_sync("agent1", "execute_tool", 130.0, is_error=True)
        collector.record_sync("agent1", "execute_tool", 110.0, is_error=False)

        # 2 errors out of 5 = 40% error rate
        summary = collector.get_operation_summary_sync("execute_tool")
        assert summary["count"] == 5
        assert summary["error_rate"] == 0.4

    def test_metrics_summary_format(self):
        """Test that summary output matches expected format."""
        collector = MetricsCollector()

        collector.record_sync("agent1", "list_servers", 45.0)
        collector.record_sync("agent1", "list_servers", 55.0)

        summary = collector.get_summary_sync()

        # Verify format
        assert "list_servers" in summary
        op_metrics = summary["list_servers"]

        # Check all expected keys
        assert "count" in op_metrics
        assert "avg_latency_ms" in op_metrics
        assert "p50_latency_ms" in op_metrics
        assert "p95_latency_ms" in op_metrics
        assert "p99_latency_ms" in op_metrics
        assert "error_rate" in op_metrics

        # Verify types
        assert isinstance(op_metrics["count"], int)
        assert isinstance(op_metrics["avg_latency_ms"], (int, float))
        assert isinstance(op_metrics["error_rate"], (int, float))

    @pytest.mark.asyncio
    async def test_metrics_concurrent_recording(self):
        """Test thread safety with concurrent metric recording."""
        collector = MetricsCollector()

        async def record_operations(agent_id: str, count: int):
            """Record multiple operations for an agent."""
            for i in range(count):
                await collector.record(
                    agent_id,
                    "test_op",
                    float(i * 10),
                    is_error=(i % 5 == 0)
                )

        # Run concurrent operations
        await asyncio.gather(
            record_operations("agent1", 50),
            record_operations("agent2", 50),
            record_operations("agent3", 50)
        )

        # Verify overall metrics
        summary = await collector.get_summary()
        assert summary["test_op"]["count"] == 150  # 50 * 3 agents

        # Verify per-agent metrics
        agent1_summary = await collector.get_agent_summary("agent1")
        assert agent1_summary["test_op"]["count"] == 50

        agent2_summary = await collector.get_agent_summary("agent2")
        assert agent2_summary["test_op"]["count"] == 50

        agent3_summary = await collector.get_agent_summary("agent3")
        assert agent3_summary["test_op"]["count"] == 50

    def test_metrics_empty_metrics(self):
        """Test that collector handles no data gracefully."""
        collector = MetricsCollector()

        # Overall summary should be empty
        summary = collector.get_summary_sync()
        assert summary == {}

        # Unknown agent should return empty dict
        agent_summary = collector.get_agent_summary_sync("unknown_agent")
        assert agent_summary == {}

        # Unknown operation should return zero metrics
        op_summary = collector.get_operation_summary_sync("unknown_op")
        assert op_summary["count"] == 0
        assert op_summary["avg_latency_ms"] == 0.0
        assert op_summary["error_rate"] == 0.0

    def test_metrics_multiple_operations(self):
        """Test tracking multiple different operations."""
        collector = MetricsCollector()

        collector.record_sync("agent1", "list_servers", 50.0)
        collector.record_sync("agent1", "get_server_tools", 100.0)
        collector.record_sync("agent1", "execute_tool", 200.0)

        summary = collector.get_summary_sync()

        assert len(summary) == 3
        assert "list_servers" in summary
        assert "get_server_tools" in summary
        assert "execute_tool" in summary

        assert summary["list_servers"]["avg_latency_ms"] == 50.0
        assert summary["get_server_tools"]["avg_latency_ms"] == 100.0
        assert summary["execute_tool"]["avg_latency_ms"] == 200.0

    def test_metrics_get_all_agents(self):
        """Test retrieving list of all tracked agents."""
        collector = MetricsCollector()

        collector.record_sync("agent1", "test_op", 10.0)
        collector.record_sync("agent2", "test_op", 20.0)
        collector.record_sync("agent3", "test_op", 30.0)

        agents = collector.get_all_agents_sync()

        assert len(agents) == 3
        assert "agent1" in agents
        assert "agent2" in agents
        assert "agent3" in agents

    def test_metrics_reset(self):
        """Test resetting all metrics."""
        collector = MetricsCollector()

        # Record some metrics
        collector.record_sync("agent1", "test_op", 100.0)
        collector.record_sync("agent2", "test_op", 200.0)

        # Verify metrics exist
        summary = collector.get_summary_sync()
        assert summary["test_op"]["count"] == 2

        # Reset
        collector.reset_sync()

        # Verify metrics are cleared
        summary = collector.get_summary_sync()
        assert summary == {}

        agents = collector.get_all_agents_sync()
        assert agents == []

    @pytest.mark.asyncio
    async def test_metrics_async_methods(self):
        """Test async versions of all methods."""
        collector = MetricsCollector()

        # Test async record
        await collector.record("agent1", "test_op", 100.0, is_error=False)
        await collector.record("agent1", "test_op", 200.0, is_error=True)

        # Test async get_summary
        summary = await collector.get_summary()
        assert summary["test_op"]["count"] == 2
        assert summary["test_op"]["error_rate"] == 0.5

        # Test async get_agent_summary
        agent_summary = await collector.get_agent_summary("agent1")
        assert agent_summary["test_op"]["count"] == 2

        # Test async get_operation_summary
        op_summary = await collector.get_operation_summary("test_op")
        assert op_summary["count"] == 2

        # Test async get_all_agents
        agents = await collector.get_all_agents()
        assert "agent1" in agents

        # Test async reset
        await collector.reset()
        summary = await collector.get_summary()
        assert summary == {}


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_zero_latency(self):
        """Test recording operations with zero latency."""
        collector = MetricsCollector()

        collector.record_sync("agent1", "test_op", 0.0)

        summary = collector.get_operation_summary_sync("test_op")
        assert summary["avg_latency_ms"] == 0.0
        assert summary["p50_latency_ms"] == 0.0

    def test_very_high_latency(self):
        """Test recording operations with very high latency."""
        collector = MetricsCollector()

        collector.record_sync("agent1", "test_op", 999999.99)

        summary = collector.get_operation_summary_sync("test_op")
        assert summary["avg_latency_ms"] == 999999.99

    def test_negative_latency_handling(self):
        """Test that negative latencies can be recorded (clock skew)."""
        collector = MetricsCollector()

        # This shouldn't happen in practice, but shouldn't crash
        collector.record_sync("agent1", "test_op", -10.0)

        summary = collector.get_operation_summary_sync("test_op")
        assert summary["count"] == 1
        assert summary["avg_latency_ms"] == -10.0

    def test_many_agents(self):
        """Test tracking many agents simultaneously."""
        collector = MetricsCollector()

        # Record operations for 100 different agents
        for i in range(100):
            collector.record_sync(f"agent_{i}", "test_op", float(i))

        agents = collector.get_all_agents_sync()
        assert len(agents) == 100

        # Overall metrics should aggregate all agents
        summary = collector.get_operation_summary_sync("test_op")
        assert summary["count"] == 100

    def test_agent_isolation(self):
        """Test that agent metrics are properly isolated."""
        collector = MetricsCollector()

        # Agent1 has only successes
        collector.record_sync("agent1", "test_op", 100.0, is_error=False)
        collector.record_sync("agent1", "test_op", 110.0, is_error=False)

        # Agent2 has only errors
        collector.record_sync("agent2", "test_op", 200.0, is_error=True)
        collector.record_sync("agent2", "test_op", 210.0, is_error=True)

        # Check agent1 has 0% error rate
        agent1_summary = collector.get_agent_summary_sync("agent1")
        assert agent1_summary["test_op"]["error_rate"] == 0.0

        # Check agent2 has 100% error rate
        agent2_summary = collector.get_agent_summary_sync("agent2")
        assert agent2_summary["test_op"]["error_rate"] == 1.0

        # Overall should be 50% error rate (2 errors out of 4)
        overall = collector.get_operation_summary_sync("test_op")
        assert overall["error_rate"] == 0.5

    def test_special_characters_in_identifiers(self):
        """Test that special characters in agent/operation names work."""
        collector = MetricsCollector()

        collector.record_sync("agent-with-dashes", "operation_with_underscores", 100.0)
        collector.record_sync("agent.with.dots", "operation:with:colons", 200.0)

        agents = collector.get_all_agents_sync()
        assert "agent-with-dashes" in agents
        assert "agent.with.dots" in agents

        summary = collector.get_summary_sync()
        assert "operation_with_underscores" in summary
        assert "operation:with:colons" in summary

    def test_percentile_with_duplicate_values(self):
        """Test percentile calculation with many duplicate values."""
        metrics = OperationMetrics()

        # Record same latency 100 times
        for _ in range(100):
            metrics.record(50.0)

        summary = metrics.get_summary()

        # All percentiles should be 50.0
        assert summary["p50_latency_ms"] == 50.0
        assert summary["p95_latency_ms"] == 50.0
        assert summary["p99_latency_ms"] == 50.0

    def test_two_values_percentile(self):
        """Test percentile calculation with exactly two values."""
        metrics = OperationMetrics()

        metrics.record(10.0)
        metrics.record(90.0)

        summary = metrics.get_summary()

        # With only 2 values, P50 should be between them
        assert 10.0 <= summary["p50_latency_ms"] <= 90.0
        assert summary["p95_latency_ms"] >= 50.0


class TestPerformance:
    """Test performance characteristics."""

    def test_recording_performance(self):
        """Test that metric recording is fast (< 1ms overhead)."""
        import time

        collector = MetricsCollector()

        # Time 1000 record operations
        start = time.perf_counter()

        for i in range(1000):
            collector.record_sync(f"agent_{i % 10}", "test_op", float(i))

        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms

        # Average per-operation should be < 1ms
        avg_per_op = elapsed / 1000
        assert avg_per_op < 1.0, f"Recording took {avg_per_op:.3f}ms per operation"

    def test_memory_usage_reasonable(self):
        """Test that memory usage stays reasonable with many operations."""
        collector = MetricsCollector()

        # Record 10,000 operations
        # Each latency is a float (8 bytes), so 10k = 80KB just for latencies
        # Plus overhead for dicts and objects
        # Should be well under 10MB
        for i in range(10000):
            collector.record_sync(f"agent_{i % 100}", "test_op", float(i))

        summary = collector.get_summary_sync()
        assert summary["test_op"]["count"] == 10000

        # This test mainly ensures we don't crash with memory errors
        # Actual memory profiling would require additional tools
