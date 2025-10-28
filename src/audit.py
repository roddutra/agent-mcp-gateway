"""Audit logging for Agent MCP Gateway."""

import json
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable


class AuditLogger:
    """Logs gateway operations for security auditing and debugging."""

    def __init__(self, log_path: str = "./logs/audit.jsonl"):
        """Initialize audit logger with log file path.

        Args:
            log_path: Path to audit log file (JSONL format)
        """
        self.log_path = Path(log_path).expanduser()
        # Create log directory if it doesn't exist
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        agent_id: str,
        operation: str,
        decision: str,
        latency_ms: float,
        metadata: dict[str, Any] | None = None
    ):
        """Log an audit entry to the log file.

        Args:
            agent_id: Agent making the request
            operation: Operation name (list_servers, execute_tool, etc.)
            decision: ALLOW, DENY, or ERROR
            latency_ms: Operation latency in milliseconds
            metadata: Additional context (server, tool, error, etc.)
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "operation": operation,
            "decision": decision,
            "latency_ms": round(latency_ms, 2),
            "metadata": metadata or {}
        }

        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()  # Ensure immediate write
        except Exception as e:
            # Log to stderr if file logging fails
            # Don't raise - logging failures shouldn't crash the gateway
            print(f"WARNING: Failed to write audit log: {e}", file=sys.stderr)


def audit_operation(operation: str, audit_logger: AuditLogger):
    """Decorator to automatically audit an operation.

    Args:
        operation: Operation name
        audit_logger: AuditLogger instance

    Returns:
        Decorated function that logs operation timing and outcome
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            agent_id = kwargs.get("agent_id", "unknown")

            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                audit_logger.log(agent_id, operation, "ALLOW", latency_ms)
                return result
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                audit_logger.log(
                    agent_id,
                    operation,
                    "ERROR",
                    latency_ms,
                    metadata={"error": str(e)}
                )
                raise

        return wrapper
    return decorator
