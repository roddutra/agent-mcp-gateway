"""Unit tests for audit logging functionality."""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import pytest
from src.audit import AuditLogger, audit_operation


class TestAuditLogger:
    """Test cases for AuditLogger class."""

    def test_log_entry_creation(self, tmp_path):
        """Test creating a basic audit log entry."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log(
            agent_id="test_agent",
            operation="test_operation",
            decision="ALLOW",
            latency_ms=123.45
        )

        # Verify file was created and entry was written
        assert log_file.exists()
        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["agent_id"] == "test_agent"
        assert entry["operation"] == "test_operation"
        assert entry["decision"] == "ALLOW"
        assert entry["latency_ms"] == 123.45
        assert "timestamp" in entry
        assert entry["metadata"] == {}

    def test_log_entry_with_metadata(self, tmp_path):
        """Test log entry with additional metadata."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        metadata = {
            "server": "postgres",
            "tool": "query",
            "result": "success"
        }

        logger.log(
            agent_id="test_agent",
            operation="execute_tool",
            decision="ALLOW",
            latency_ms=250.0,
            metadata=metadata
        )

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["metadata"]["server"] == "postgres"
        assert entry["metadata"]["tool"] == "query"
        assert entry["metadata"]["result"] == "success"

    def test_jsonl_format(self, tmp_path):
        """Test that log file uses JSONL format (one JSON object per line)."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        # Log multiple entries
        for i in range(3):
            logger.log(
                agent_id=f"agent_{i}",
                operation=f"operation_{i}",
                decision="ALLOW",
                latency_ms=float(i * 100)
            )

        # Verify each line is valid JSON
        with open(log_file, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 3

        for i, line in enumerate(lines):
            entry = json.loads(line.strip())
            assert entry["agent_id"] == f"agent_{i}"
            assert entry["operation"] == f"operation_{i}"

    def test_iso8601_timestamp_format(self, tmp_path):
        """Test that timestamps are in ISO 8601 format with timezone."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "test_op", "ALLOW", 10.0)

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        timestamp = entry["timestamp"]

        # Verify ISO 8601 format with timezone
        # Should be like: 2024-01-15T12:34:56.789123+00:00
        parsed = datetime.fromisoformat(timestamp)
        assert parsed.tzinfo is not None  # Has timezone
        assert parsed.tzinfo == timezone.utc or parsed.tzinfo.utcoffset(None) == timezone.utc.utcoffset(None)

    def test_latency_rounding(self, tmp_path):
        """Test that latency is rounded to 2 decimal places."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "test_op", "ALLOW", 123.456789)

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["latency_ms"] == 123.46  # Rounded to 2 decimals

    def test_log_file_creation_in_new_directory(self, tmp_path):
        """Test that log directory is created if it doesn't exist."""
        log_file = tmp_path / "new" / "nested" / "directory" / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "test_op", "ALLOW", 10.0)

        assert log_file.exists()
        assert log_file.parent.exists()

    def test_log_appending(self, tmp_path):
        """Test that logging appends to existing file (doesn't overwrite)."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        # Log first entry
        logger.log("agent1", "op1", "ALLOW", 10.0)

        # Create new logger instance and log second entry
        logger2 = AuditLogger(str(log_file))
        logger2.log("agent2", "op2", "DENY", 20.0)

        # Verify both entries exist
        with open(log_file, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])

        assert entry1["agent_id"] == "agent1"
        assert entry2["agent_id"] == "agent2"

    def test_file_flush_for_immediate_writes(self, tmp_path):
        """Test that log entries are flushed immediately."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "test_op", "ALLOW", 10.0)

        # Read immediately - should be available due to flush
        with open(log_file, 'r') as f:
            content = f.read()

        assert len(content) > 0
        entry = json.loads(content.strip())
        assert entry["agent_id"] == "test"

    def test_graceful_error_handling(self, tmp_path, capsys):
        """Test that logging errors don't crash the application."""
        # Create a read-only directory to trigger write error
        log_dir = tmp_path / "readonly"
        log_dir.mkdir()
        log_file = log_dir / "audit.jsonl"

        # Make directory read-only after creation (Unix-like systems)
        try:
            log_dir.chmod(0o444)

            logger = AuditLogger(str(log_file))

            # This should not raise an exception, but log to stderr
            logger.log("test", "test_op", "ALLOW", 10.0)

            # Verify warning was written to stderr
            captured = capsys.readouterr()
            assert "WARNING" in captured.err or "Failed to write audit log" in captured.err or len(captured.err) > 0

        finally:
            # Restore permissions for cleanup
            log_dir.chmod(0o755)

    def test_multiple_log_entries_no_corruption(self, tmp_path):
        """Test that multiple rapid log entries don't corrupt the file."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        # Log many entries rapidly
        for i in range(100):
            logger.log(f"agent_{i}", f"op_{i}", "ALLOW", float(i))

        # Verify all entries are valid JSON
        with open(log_file, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 100

        for i, line in enumerate(lines):
            entry = json.loads(line.strip())  # Should not raise
            assert entry["agent_id"] == f"agent_{i}"

    def test_metadata_field_optional(self, tmp_path):
        """Test that metadata field is optional."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        # Log without metadata
        logger.log("test", "test_op", "ALLOW", 10.0)

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert "metadata" in entry
        assert entry["metadata"] == {}

    def test_all_decision_types(self, tmp_path):
        """Test logging different decision types (ALLOW, DENY, ERROR)."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "op1", "ALLOW", 10.0)
        logger.log("test", "op2", "DENY", 20.0)
        logger.log("test", "op3", "ERROR", 30.0, metadata={"error": "test error"})

        with open(log_file, 'r') as f:
            lines = f.readlines()

        decisions = [json.loads(line)["decision"] for line in lines]
        assert decisions == ["ALLOW", "DENY", "ERROR"]


class TestAuditOperationDecorator:
    """Test cases for audit_operation decorator."""

    @pytest.mark.asyncio
    async def test_decorator_timing(self, tmp_path):
        """Test that decorator correctly measures operation timing."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        @audit_operation("test_operation", logger)
        async def test_function(agent_id: str):
            await asyncio_sleep(0.1)  # Sleep for 100ms
            return "success"

        result = await test_function(agent_id="test_agent")

        assert result == "success"

        # Check log entry
        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["operation"] == "test_operation"
        assert entry["agent_id"] == "test_agent"
        assert entry["decision"] == "ALLOW"
        # Latency should be >= 100ms
        assert entry["latency_ms"] >= 100.0

    @pytest.mark.asyncio
    async def test_decorator_error_handling(self, tmp_path):
        """Test that decorator logs errors correctly."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        @audit_operation("failing_operation", logger)
        async def failing_function(agent_id: str):
            raise ValueError("Test error")

        # Function should still raise the exception
        with pytest.raises(ValueError) as exc_info:
            await failing_function(agent_id="test_agent")

        assert "Test error" in str(exc_info.value)

        # Check that error was logged
        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["operation"] == "failing_operation"
        assert entry["agent_id"] == "test_agent"
        assert entry["decision"] == "ERROR"
        assert "error" in entry["metadata"]
        assert "Test error" in entry["metadata"]["error"]

    @pytest.mark.asyncio
    async def test_decorator_extracts_agent_id(self, tmp_path):
        """Test that decorator extracts agent_id from kwargs."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        @audit_operation("test_op", logger)
        async def test_func(server: str, agent_id: str, tool: str):
            return f"{server}:{tool}"

        result = await test_func(server="api", agent_id="my_agent", tool="query")

        assert result == "api:query"

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["agent_id"] == "my_agent"

    @pytest.mark.asyncio
    async def test_decorator_unknown_agent_fallback(self, tmp_path):
        """Test that decorator uses 'unknown' when agent_id not in kwargs."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        @audit_operation("test_op", logger)
        async def test_func(data: str):
            return data

        result = await test_func(data="test")

        assert result == "test"

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["agent_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self, tmp_path):
        """Test that decorator preserves original function metadata."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        @audit_operation("test_op", logger)
        async def documented_function(agent_id: str):
            """This is a documented function."""
            return "result"

        # functools.wraps should preserve metadata
        assert documented_function.__name__ == "documented_function"
        assert "documented function" in documented_function.__doc__

    @pytest.mark.asyncio
    async def test_decorator_with_multiple_calls(self, tmp_path):
        """Test decorator with multiple sequential calls."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        @audit_operation("multi_op", logger)
        async def test_func(agent_id: str, value: int):
            return value * 2

        # Make multiple calls
        await test_func(agent_id="agent1", value=10)
        await test_func(agent_id="agent2", value=20)
        await test_func(agent_id="agent3", value=30)

        # Verify all logged
        with open(log_file, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 3

        agents = [json.loads(line)["agent_id"] for line in lines]
        assert agents == ["agent1", "agent2", "agent3"]


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_log_with_empty_metadata(self, tmp_path):
        """Test logging with explicitly empty metadata."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "test_op", "ALLOW", 10.0, metadata={})

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["metadata"] == {}

    def test_log_with_complex_metadata(self, tmp_path):
        """Test logging with complex nested metadata."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        metadata = {
            "server": "postgres",
            "details": {
                "query": "SELECT * FROM users",
                "rows": 42,
                "cached": True
            },
            "tags": ["database", "read-only"]
        }

        logger.log("test", "test_op", "ALLOW", 10.0, metadata=metadata)

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["metadata"]["server"] == "postgres"
        assert entry["metadata"]["details"]["rows"] == 42
        assert "database" in entry["metadata"]["tags"]

    def test_log_with_special_characters(self, tmp_path):
        """Test logging with special characters in strings."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log(
            agent_id="agent_with_unicode_文字",
            operation="test\"quotes'single",
            decision="ALLOW",
            latency_ms=10.0,
            metadata={"message": "Line1\nLine2\tTab"}
        )

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert "文字" in entry["agent_id"]
        assert "quotes" in entry["operation"]
        assert "\n" in entry["metadata"]["message"]

    def test_zero_latency(self, tmp_path):
        """Test logging with zero latency."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "test_op", "ALLOW", 0.0)

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["latency_ms"] == 0.0

    def test_very_high_latency(self, tmp_path):
        """Test logging with very high latency values."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log("test", "test_op", "ALLOW", 999999.999)

        with open(log_file, 'r') as f:
            entry = json.loads(f.readline())

        assert entry["latency_ms"] == 1000000.0  # Rounded

    def test_path_with_tilde_expansion(self, tmp_path, monkeypatch):
        """Test that tilde in path is expanded."""
        monkeypatch.setenv("HOME", str(tmp_path))

        logger = AuditLogger("~/audit.jsonl")
        logger.log("test", "test_op", "ALLOW", 10.0)

        # Verify file was created in expanded path
        expected_path = tmp_path / "audit.jsonl"
        assert expected_path.exists()


# Helper function for async sleep (not importing asyncio to keep test simple)
async def asyncio_sleep(seconds):
    """Simple async sleep implementation for tests."""
    import asyncio
    await asyncio.sleep(seconds)
