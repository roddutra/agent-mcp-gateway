# Milestone 1: Core Functionality

**Status:** ✅ COMPLETE
**Target:** Complete gateway functionality with tool discovery, execution, and session isolation
**Completion Date:** October 29, 2025

---

## Overview

M1 implements the core proxying functionality that makes the gateway useful. This milestone adds:
- `get_server_tools` tool for on-demand tool discovery with filtering
- `execute_tool` for transparent proxying to downstream servers
- Session isolation using ProxyClient for concurrent safety
- Middleware for access control enforcement
- Metrics collection for monitoring

**Key Success Metric:** Agents can discover and execute tools from downstream servers through the gateway with <100ms added latency and full policy enforcement.

---

## Core Components

### 1. Proxy Infrastructure
### 2. get_server_tools Tool
### 3. execute_tool Tool
### 4. Access Control Middleware
### 5. Session Management
### 6. Metrics Collection

---

## Detailed Task Checklist

### Proxy Infrastructure Setup

- [x] Integrate FastMCP.as_proxy() for downstream connections
  - [x] Create proxy connections to all configured servers
  - [x] Use `ProxyClient` for session isolation
  - [x] Handle both stdio and HTTP transports automatically
  - [x] Store proxy connections in gateway state
  - [x] Implement lazy connection strategy (connect on first use)

- [x] Update gateway initialization
  - [x] Create proxy connections for all servers in mcp_config
  - [x] Store server→ProxyClient mapping in state
  - [x] Handle connection failures gracefully
  - [x] Implement connection retry logic
  - [x] Log connection status for each server

**Code Reference:**
```python
from fastmcp import FastMCP
from fastmcp.server.proxy import ProxyClient
from typing import Dict
import logging

logger = logging.getLogger(__name__)

async def initialize_proxy_connections(mcp_config: dict) -> Dict[str, ProxyClient]:
    """Initialize proxy connections to all configured MCP servers."""
    proxy_clients = {}
    servers = mcp_config.get("mcpServers", {})

    for server_name, server_config in servers.items():
        try:
            # Create ProxyClient based on transport type
            if "command" in server_config:
                # Stdio transport
                client = ProxyClient(
                    command=server_config["command"],
                    args=server_config.get("args", []),
                    env=server_config.get("env", {})
                )
            elif "url" in server_config:
                # HTTP transport
                client = ProxyClient(
                    url=server_config["url"],
                    headers=server_config.get("headers", {})
                )
            else:
                logger.error(f"Invalid config for server {server_name}")
                continue

            proxy_clients[server_name] = client
            logger.info(f"Initialized proxy for {server_name}")

        except Exception as e:
            logger.error(f"Failed to initialize proxy for {server_name}: {e}")
            # Continue with other servers

    return proxy_clients
```

**Documentation Reference:**
- FastMCP ProxyClient - https://gofastmcp.com/servers/proxy#quick-start
- Session Isolation - https://gofastmcp.com/servers/proxy#session-isolation-concurrency

### get_server_tools Tool Implementation

- [x] Implement get_server_tools tool
  - [x] Add `@gateway.tool` decorator
  - [x] Require `agent_id: str` and `server: str` parameters
  - [x] Add optional `names: list[str] | None` for specific tools
  - [x] Add optional `pattern: str | None` for wildcard filtering
  - [x] Add optional `max_schema_tokens: int | None` for budget limiting
  - [x] Verify agent has access to requested server
  - [x] Connect to downstream server via ProxyClient
  - [x] List tools from downstream server
  - [x] Filter tools based on agent policies
  - [x] Apply pattern matching if specified
  - [x] Estimate and limit schema tokens if budget specified
  - [x] Return tool definitions with schemas

- [x] Implement tool filtering logic
  - [x] Filter by explicit tool names list
  - [x] Support wildcard patterns (e.g., `get_*`, `*_user`)
  - [x] Apply agent policy rules
  - [x] Combine multiple filter criteria

- [x] Implement schema token estimation
  - [x] Count tokens in tool name, description, input schema
  - [x] Track cumulative token count
  - [x] Stop including tools when budget exceeded
  - [x] Return partial list with indicator if truncated

**Code Reference:**
```python
@gateway.tool
async def get_server_tools(
    agent_id: str,
    server: str,
    ctx: Context,
    names: list[str] | None = None,
    pattern: str | None = None,
    max_schema_tokens: int | None = None
) -> dict:
    """
    Get tool definitions from a specific MCP server, filtered by agent permissions.

    Args:
        agent_id: Identifier of the agent making the request
        server: Name of the downstream MCP server
        names: Optional list of specific tool names to retrieve
        pattern: Optional wildcard pattern for tool names (e.g., "get_*")
        max_schema_tokens: Optional token budget limit for schemas

    Returns:
        Dictionary with tools list and metadata
    """
    import time
    start_time = time.time()

    # Get dependencies from context
    policy_engine: PolicyEngine = ctx.get_state("policy_engine")
    proxy_clients: Dict[str, ProxyClient] = ctx.get_state("proxy_clients")
    audit_logger: AuditLogger = ctx.get_state("audit_logger")

    # Verify agent can access this server
    if not policy_engine.can_access_server(agent_id, server):
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "get_server_tools", "DENY", latency_ms,
                        {"server": server, "reason": "server_not_allowed"})
        return {
            "tools": [],
            "error": f"Agent '{agent_id}' cannot access server '{server}'"
        }

    # Get proxy client for server
    if server not in proxy_clients:
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "get_server_tools", "ERROR", latency_ms,
                        {"server": server, "reason": "server_not_found"})
        return {
            "tools": [],
            "error": f"Server '{server}' not found"
        }

    proxy_client = proxy_clients[server]

    # Connect and list tools from downstream server
    try:
        async with proxy_client:
            tools = await proxy_client.list_tools()
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "get_server_tools", "ERROR", latency_ms,
                        {"server": server, "error": str(e)})
        return {
            "tools": [],
            "error": f"Failed to connect to server: {str(e)}"
        }

    # Filter tools
    filtered_tools = []
    token_count = 0

    for tool in tools:
        # Check if tool matches filters
        if names and tool.name not in names:
            continue

        if pattern and not _matches_pattern(tool.name, pattern):
            continue

        # Check agent policy
        if not policy_engine.can_access_tool(agent_id, server, tool.name):
            continue

        # Check token budget
        if max_schema_tokens:
            tool_tokens = _estimate_tool_tokens(tool)
            if token_count + tool_tokens > max_schema_tokens:
                break
            token_count += tool_tokens

        # Convert to dict format
        filtered_tools.append({
            "name": tool.name,
            "description": tool.description or "",
            "inputSchema": tool.inputSchema
        })

    latency_ms = (time.time() - start_time) * 1000
    audit_logger.log(agent_id, "get_server_tools", "ALLOW", latency_ms, {
        "server": server,
        "tools_requested": len(tools),
        "tools_returned": len(filtered_tools),
        "token_count": token_count
    })

    return {
        "tools": filtered_tools,
        "server": server,
        "total_available": len(tools),
        "returned": len(filtered_tools),
        "tokens_used": token_count if max_schema_tokens else None
    }

def _matches_pattern(tool_name: str, pattern: str) -> bool:
    """Check if tool name matches wildcard pattern."""
    import re
    # Convert wildcard pattern to regex
    regex_pattern = pattern.replace("*", ".*")
    return re.match(f"^{regex_pattern}$", tool_name) is not None

def _estimate_tool_tokens(tool) -> int:
    """Estimate token count for tool definition."""
    # Rough estimation: 1 token ≈ 4 characters
    text = tool.name + (tool.description or "")
    schema_text = str(tool.inputSchema)
    return len(text + schema_text) // 4
```

**Documentation Reference:**
- FastMCP Client Operations - https://gofastmcp.com/clients/client
- MCP Tools Specification - https://modelcontextprotocol.io/specification/2025-06-18/server/tools

### execute_tool Tool Implementation

- [x] Implement execute_tool tool
  - [x] Add `@gateway.tool` decorator
  - [x] Require `agent_id: str`, `server: str`, `tool: str`, `args: dict` parameters
  - [x] Add optional `timeout_ms: int | None` parameter
  - [x] Verify agent has access to server and tool
  - [x] Get ProxyClient for server
  - [x] Execute tool on downstream server
  - [x] Apply timeout if specified
  - [x] Handle tool execution errors
  - [x] Return result transparently
  - [x] Record execution metrics

- [x] Implement transparent result forwarding
  - [x] Preserve all result content types (text, image, resource, etc.)
  - [x] Forward isError flag from downstream
  - [x] Maintain result structure exactly
  - [x] Do not modify tool responses

- [x] Add timeout handling
  - [x] Use asyncio.wait_for for timeout enforcement
  - [x] Return clear timeout error to agent
  - [x] Log timeout events

**Code Reference:**
```python
import asyncio

@gateway.tool
async def execute_tool(
    agent_id: str,
    server: str,
    tool: str,
    args: dict,
    ctx: Context,
    timeout_ms: int | None = None
) -> dict:
    """
    Execute a tool on a downstream MCP server with transparent proxying.

    Args:
        agent_id: Identifier of the agent making the request
        server: Name of the downstream MCP server
        tool: Name of the tool to execute
        args: Arguments to pass to the tool
        timeout_ms: Optional timeout in milliseconds

    Returns:
        Tool execution result (transparently forwarded from downstream)
    """
    import time
    start_time = time.time()

    # Get dependencies
    policy_engine: PolicyEngine = ctx.get_state("policy_engine")
    proxy_clients: Dict[str, ProxyClient] = ctx.get_state("proxy_clients")
    audit_logger: AuditLogger = ctx.get_state("audit_logger")

    # Verify agent can access this server
    if not policy_engine.can_access_server(agent_id, server):
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "execute_tool", "DENY", latency_ms, {
            "server": server,
            "tool": tool,
            "reason": "server_not_allowed"
        })
        raise ToolError(f"Agent '{agent_id}' cannot access server '{server}'")

    # Verify agent can access this tool
    if not policy_engine.can_access_tool(agent_id, server, tool):
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "execute_tool", "DENY", latency_ms, {
            "server": server,
            "tool": tool,
            "reason": "tool_not_allowed",
            "rule": policy_engine.get_deny_rule(agent_id, server, tool)
        })
        raise ToolError(f"Agent '{agent_id}' not authorized to call tool '{tool}'")

    # Get proxy client
    if server not in proxy_clients:
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "execute_tool", "ERROR", latency_ms, {
            "server": server,
            "tool": tool,
            "reason": "server_not_found"
        })
        raise ToolError(f"Server '{server}' not found")

    proxy_client = proxy_clients[server]

    # Execute tool with timeout
    try:
        async with proxy_client:
            if timeout_ms:
                result = await asyncio.wait_for(
                    proxy_client.call_tool(tool, args),
                    timeout=timeout_ms / 1000.0
                )
            else:
                result = await proxy_client.call_tool(tool, args)

        # Record successful execution
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "execute_tool", "ALLOW", latency_ms, {
            "server": server,
            "tool": tool,
            "is_error": getattr(result, "isError", False)
        })

        # Return result transparently
        return {
            "content": result.content,
            "isError": getattr(result, "isError", False)
        }

    except asyncio.TimeoutError:
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "execute_tool", "TIMEOUT", latency_ms, {
            "server": server,
            "tool": tool,
            "timeout_ms": timeout_ms
        })
        raise ToolError(f"Tool execution timed out after {timeout_ms}ms")

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        audit_logger.log(agent_id, "execute_tool", "ERROR", latency_ms, {
            "server": server,
            "tool": tool,
            "error": str(e)
        })
        raise ToolError(f"Tool execution failed: {str(e)}")
```

**Documentation Reference:**
- FastMCP Client Tools - https://gofastmcp.com/clients/tools
- MCP Tool Execution - https://modelcontextprotocol.io/specification/2025-06-18/server/tools

### Access Control Middleware

- [x] Implement AgentAccessControl middleware
  - [x] Extend `fastmcp.server.middleware.Middleware` base class
  - [x] Implement `on_call_tool` hook for tool execution control
  - [x] Implement `on_list_tools` hook for tool discovery filtering
  - [x] Extract agent_id from tool arguments
  - [x] Enforce access policies
  - [x] Keep agent_id in arguments (gateway tools need it for authorization)
  - [x] Handle missing agent_id based on config

- [x] Add middleware to gateway
  - [x] Register middleware with `gateway.add_middleware()`
  - [x] Ensure middleware runs before tool execution
  - [x] Test middleware isolation

**Code Reference:**
```python
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError

class AgentAccessControl(Middleware):
    """
    Middleware to enforce per-agent access rules for tools.
    """

    def __init__(self, policy_engine: PolicyEngine):
        self.policy_engine = policy_engine

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Enforce access rules on tool calls."""

        tool_call = context.message
        arguments = tool_call.arguments or {}

        # Extract agent identity
        agent_id = arguments.get("agent_id")

        if not agent_id:
            # Check default policy
            if self.policy_engine.defaults.get("deny_on_missing_agent", True):
                raise ToolError("Missing required parameter: agent_id")
            agent_id = "default"

        # Store agent in context state for logging
        context.set_state("current_agent", agent_id)

        # Gateway tools (list_servers, get_server_tools, execute_tool)
        # handle their own authorization, so we allow them through
        # The tools themselves will enforce policies

        # NOTE: We do NOT remove agent_id from arguments because the gateway
        # tools need it as a parameter to perform their authorization checks.
        # If we ever add direct proxying to downstream servers in the future,
        # we would need to remove it at that point.

        # Continue processing
        return await call_next(context)

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        """
        Filter tools list based on agent permissions.
        For the gateway, we always show all gateway tools since
        each tool does its own authorization.
        """
        # Get full tool list
        response = await call_next(context)

        # Gateway tools are always visible - they do their own auth
        # No filtering needed at middleware level

        return response
```

**Documentation Reference:**
- FastMCP Middleware - https://gofastmcp.com/servers/middleware
- Middleware Hooks - https://gofastmcp.com/servers/middleware#available-hooks

### Session Management

- [x] Implement session isolation
  - [x] Use disconnected ProxyClient instances (default behavior)
  - [x] Each tool execution gets fresh backend session
  - [x] Prevent context mixing between concurrent requests
  - [x] Document session lifecycle

- [ ] Add connection pooling (optional optimization) - DEFERRED TO FUTURE
  - [ ] Implement connection reuse for performance
  - [ ] Add connection pool configuration
  - [ ] Handle connection lifecycle properly

**Code Reference:**
```python
# Session isolation is automatic with ProxyClient
# Each request creates a fresh connection:

async def execute_with_isolation(server: str, tool: str, args: dict):
    proxy_client = proxy_clients[server]  # Disconnected client

    # This creates a fresh session for this request
    async with proxy_client:
        result = await proxy_client.call_tool(tool, args)

    # Session is closed after this block
    return result
```

**Documentation Reference:**
- Session Isolation - https://gofastmcp.com/servers/proxy#session-isolation-concurrency

### Metrics Collection

- [x] Implement metrics collector
  - [x] Track tool execution counts per server
  - [x] Track latency distributions (p50, p95, p99)
  - [x] Track error rates
  - [x] Track policy denials
  - [x] Support metrics export (stdout, file, or endpoint)

- [x] Add metrics to audit log
  - [x] Include latency_ms in all operations
  - [x] Track operation type counts
  - [x] Support aggregation queries

- [ ] Create metrics dashboard (optional) - DEFERRED TO M2
  - [ ] Simple text-based metrics output
  - [ ] Show per-agent statistics
  - [ ] Show per-server statistics

**Code Reference:**
```python
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List
import statistics

@dataclass
class OperationMetrics:
    count: int = 0
    total_latency_ms: float = 0.0
    latencies: List[float] = None
    errors: int = 0

    def __post_init__(self):
        if self.latencies is None:
            self.latencies = []

class MetricsCollector:
    """Collect and aggregate gateway metrics."""

    def __init__(self):
        self.operations: Dict[str, OperationMetrics] = defaultdict(OperationMetrics)
        self.agents: Dict[str, Dict[str, OperationMetrics]] = defaultdict(
            lambda: defaultdict(OperationMetrics)
        )

    def record(self, agent_id: str, operation: str, latency_ms: float,
               is_error: bool = False):
        """Record an operation metric."""
        # Overall metrics
        metrics = self.operations[operation]
        metrics.count += 1
        metrics.total_latency_ms += latency_ms
        metrics.latencies.append(latency_ms)
        if is_error:
            metrics.errors += 1

        # Per-agent metrics
        agent_metrics = self.agents[agent_id][operation]
        agent_metrics.count += 1
        agent_metrics.total_latency_ms += latency_ms
        agent_metrics.latencies.append(latency_ms)
        if is_error:
            agent_metrics.errors += 1

    def get_summary(self) -> dict:
        """Get metrics summary."""
        summary = {}

        for operation, metrics in self.operations.items():
            if metrics.count > 0:
                summary[operation] = {
                    "count": metrics.count,
                    "avg_latency_ms": metrics.total_latency_ms / metrics.count,
                    "p95_latency_ms": statistics.quantiles(metrics.latencies, n=20)[18]
                        if len(metrics.latencies) >= 20 else max(metrics.latencies),
                    "error_rate": metrics.errors / metrics.count
                }

        return summary
```

### Hot Configuration Reload

- [x] Add watchdog dependency
  - [x] Update pyproject.toml with watchdog package
  - [x] Run `uv sync` to install

- [x] Create ConfigWatcher class (src/config_watcher.py)
  - [x] Implement file system monitoring for both config files
  - [x] Add debouncing logic (100ms default) for rapid saves
  - [x] Create callback system for reload notifications
  - [x] Handle file events (modified, created, moved, atomic writes)
  - [x] Add logging for config change detection

- [x] Add validation framework (src/config.py)
  - [x] Implement `validate_mcp_config(config: dict) -> bool`
  - [x] Implement `validate_gateway_rules(rules: dict) -> bool`
  - [x] Add `reload_configs()` function with validation
  - [x] Store config file paths for reloading
  - [x] Return validation errors with helpful messages
  - [x] **Enhancement:** Treat undefined server references as warnings (not errors)
  - [x] Store warnings for diagnostic access via `get_last_validation_warnings()`

- [x] Implement PolicyEngine reload (src/policy.py)
  - [x] Add `reload(new_rules: dict) -> bool` method
  - [x] Validate rules before applying
  - [x] Atomic swap of internal rules dictionary with thread safety (RLock)
  - [x] Add logging for rule changes (added/removed/modified)
  - [x] Handle validation failures gracefully with rollback

- [x] Implement ProxyManager reload (src/proxy.py)
  - [x] Add `reload(new_config: dict) -> bool` method
  - [x] Compare old vs new server configurations
  - [x] Add new servers dynamically
  - [x] Remove deleted servers and clean up connections
  - [x] Update changed server configurations
  - [x] Validate server configs before applying
  - [x] Handle connection failures for new servers

- [x] Integrate ConfigWatcher in main (main.py)
  - [x] Initialize ConfigWatcher with config file paths
  - [x] Register reload callback for PolicyEngine
  - [x] Register reload callback for ProxyManager
  - [x] Add error handling for reload failures
  - [x] Log reload success/failure events with timestamps
  - [x] Ensure graceful degradation on reload errors
  - [x] **Enhancement:** Track reload status (attempts, successes, errors, warnings)
  - [x] Expose reload status via `get_reload_status()` function

- [x] Create diagnostic tool (src/gateway.py)
  - [x] Implement `get_gateway_status` tool for health checks
  - [x] Return reload status, policy state, available servers, config paths
  - [x] Enable agents to programmatically check gateway health

- [x] Create unit tests
  - [x] tests/test_config_watcher.py (35 tests: file watching, debouncing, callbacks)
  - [x] tests/test_validation_and_reload.py (54 tests: validation, rollback scenarios)
  - [x] Add reload tests to test_policy.py (10 tests)
  - [x] Add reload tests to test_proxy.py (13 tests)
  - [x] tests/test_hot_reload_e2e.py (11 tests: end-to-end validation fix verification)

- [x] Create integration tests
  - [x] tests/test_integration_reload.py (20 tests: end-to-end reload)
  - [x] Test file modification triggers reload
  - [x] Test validation failures preserve old config
  - [x] Test in-flight operations unaffected by reload
  - [x] Test new operations use new config
  - [x] Test concurrent reloads handled safely

**Key Enhancements:**
- **Flexible Validation:** Rules can reference servers not currently in .mcp.json (logged as warnings)
- **Thread Safety:** All PolicyEngine operations protected with RLock
- **Visibility:** Reload status tracking and diagnostic tool for troubleshooting
- **Robustness:** 420 tests with 100% hot reload coverage

### Integration & Testing

- [x] Update main.py with all new components
  - [x] Initialize proxy connections
  - [x] Register middleware
  - [x] Initialize metrics collector
  - [x] Add all three gateway tools

- [x] Create integration tests
  - [x] Test get_server_tools with various filters
  - [x] Test execute_tool end-to-end
  - [x] Test policy enforcement
  - [x] Test session isolation
  - [x] Test concurrent requests
  - [x] Test timeout handling

- [x] Create performance tests
  - [x] Measure execute_tool overhead (<30ms target)
  - [x] Measure get_server_tools performance (<300ms target)
  - [x] Test under concurrent load
  - [x] Verify session isolation doesn't leak memory

**Code Reference:**
```python
# tests/test_integration.py
import pytest
from fastmcp import Client

@pytest.mark.asyncio
async def test_full_workflow():
    """Test complete workflow: list servers → get tools → execute tool."""

    async with Client("main.py") as client:
        # 1. List servers
        servers = await client.call_tool("list_servers", {
            "agent_id": "researcher"
        })
        assert "brave-search" in [s["name"] for s in servers.data]

        # 2. Get tools from server
        tools = await client.call_tool("get_server_tools", {
            "agent_id": "researcher",
            "server": "brave-search"
        })
        assert len(tools.data["tools"]) > 0

        # 3. Execute a tool (assuming brave-search has a search tool)
        result = await client.call_tool("execute_tool", {
            "agent_id": "researcher",
            "server": "brave-search",
            "tool": "brave_web_search",
            "args": {"query": "FastMCP documentation"}
        })
        assert not result.data.get("isError")
        assert len(result.data.get("content", [])) > 0
```

---

## Success Criteria

### Functional Requirements
- [x] All three gateway tools (list_servers, get_server_tools, execute_tool) work
- [x] Tools are filtered correctly based on agent policies
- [x] Tool execution results are transparently forwarded
- [x] Session isolation prevents context mixing
- [x] Middleware enforces access control
- [x] Metrics are collected for all operations
- [x] Hot configuration reload works automatically
  - [x] File changes detected within 500ms
  - [x] Invalid configs rejected with old config preserved
  - [x] In-flight operations complete with old config
  - [x] New operations use new config immediately
  - [x] Undefined server references treated as warnings (not errors)
  - [x] Reload status tracked and accessible via diagnostic tool

### Performance Requirements
- [x] execute_tool overhead: <30ms (P95) - **Actual: ~5ms (83% better)**
- [x] get_server_tools: <300ms (P95) - **Actual: ~7ms (98% better)**
- [x] No memory leaks under sustained load - **Tested with 10,000 operations**
- [x] Concurrent requests handled safely - **Tested with 30 simultaneous requests**

### Quality Requirements
- [x] All error codes implemented (DENIED_BY_POLICY, SERVER_UNAVAILABLE, TOOL_NOT_FOUND, TIMEOUT)
- [x] Clear error messages for all failure modes
- [x] Comprehensive test coverage (>80%) - **Actual: 92% coverage**
- [x] Integration tests pass - **24 integration tests, all passing**

---

## Performance Targets

| Operation | Target (P95) | Measurement Method |
|-----------|--------------|-------------------|
| list_servers | <50ms | Time from call to response |
| get_server_tools | <300ms | Including downstream server connection |
| execute_tool overhead | <30ms | Gateway time, excluding downstream execution |

---

## Dependencies

**External:**
- FastMCP 2.13.0.1+
- Python 3.12+
- ProxyClient from FastMCP

**Internal:**
- M0 (Foundation) must be complete
- Requires config loading, policy engine, audit logging from M0

---

## Documentation References

- **FastMCP Proxy:** https://gofastmcp.com/servers/proxy
- **FastMCP ProxyClient:** https://gofastmcp.com/servers/proxy#quick-start
- **FastMCP Middleware:** https://gofastmcp.com/servers/middleware
- **FastMCP Client:** https://gofastmcp.com/clients/client
- **MCP Tools:** https://modelcontextprotocol.io/specification/2025-06-18/server/tools

---

## Notes

- ProxyClient provides automatic session isolation - each request gets a fresh session
- Middleware runs for all tool calls, but gateway tools do their own authorization
- Token estimation for max_schema_tokens is approximate - adjust algorithm as needed
- Consider adding caching for get_server_tools results in future optimization
- Error handling should distinguish between gateway errors and downstream errors
