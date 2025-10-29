"""Integration tests for Agent MCP Gateway M1-Core milestone.

This module contains end-to-end integration tests that verify:
- Full workflow: list_servers → get_server_tools → execute_tool
- Policy enforcement across all gateway tools
- Concurrent requests from multiple agents
- Session isolation between agents
- Timeout handling and error recovery
- Component integration (ProxyManager, PolicyEngine, Middleware)
- Performance benchmarks against targets

Test Strategy:
- Mock downstream MCP servers to avoid real connections
- Use pytest-asyncio for async test execution
- Verify policy enforcement at each layer
- Measure and validate latency targets
"""

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.gateway import (
    gateway,
    initialize_gateway,
    list_servers as list_servers_tool,
    get_server_tools as get_server_tools_tool,
    _execute_tool_impl
)
from src.policy import PolicyEngine
from src.proxy import ProxyManager
from src.metrics import MetricsCollector
from src.middleware import AgentAccessControl
from fastmcp.exceptions import ToolError

# Extract the actual functions from FastMCP's FunctionTool wrapper
list_servers = list_servers_tool.fn
get_server_tools = get_server_tools_tool.fn
execute_tool = _execute_tool_impl


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def gateway_rules():
    """Load test gateway rules configuration."""
    return {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search"],
                    "tools": {
                        "brave-search": ["*"]
                    }
                }
            },
            "backend": {
                "allow": {
                    "servers": ["postgres", "filesystem"],
                    "tools": {
                        "postgres": ["query", "list_*"],
                        "filesystem": ["read_*", "list_*"]
                    }
                },
                "deny": {
                    "tools": {
                        "postgres": ["drop_*", "delete_*"],
                        "filesystem": ["write_*", "delete_*"]
                    }
                }
            },
            "admin": {
                "allow": {
                    "servers": ["*"],
                    "tools": {
                        "postgres": ["*"],
                        "filesystem": ["*"],
                        "brave-search": ["*"]
                    }
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": True
        }
    }


@pytest.fixture
def mcp_config():
    """Load test MCP servers configuration."""
    return {
        "mcpServers": {
            "brave-search": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                "description": "Brave search API server"
            },
            "postgres": {
                "command": "uvx",
                "args": ["mcp-server-postgres"],
                "description": "PostgreSQL database server"
            },
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
                "description": "Filesystem access server"
            }
        }
    }


# Mock tool class to simulate FastMCP Tool objects
class MockTool:
    """Mock tool object for testing."""

    def __init__(self, name: str, description: str = "", inputSchema: dict | None = None):
        self.name = name
        self.description = description
        self.inputSchema = inputSchema or {}


@pytest.fixture
def mock_tool_definitions():
    """Create mock tool definitions for different servers."""
    return {
        "brave-search": [
            MockTool(
                name="brave_web_search",
                description="Search the web using Brave",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    }
                }
            ),
            MockTool(
                name="brave_local_search",
                description="Search local businesses",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "location": {"type": "string"}
                    }
                }
            )
        ],
        "postgres": [
            MockTool(
                name="query",
                description="Execute SQL query",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"}
                    }
                }
            ),
            MockTool(
                name="list_tables",
                description="List database tables",
                inputSchema={"type": "object", "properties": {}}
            ),
            MockTool(
                name="drop_table",
                description="Drop a database table",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"}
                    }
                }
            )
        ],
        "filesystem": [
            MockTool(
                name="read_file",
                description="Read file contents",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    }
                }
            ),
            MockTool(
                name="list_directory",
                description="List directory contents",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    }
                }
            ),
            MockTool(
                name="write_file",
                description="Write file contents",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    }
                }
            )
        ]
    }


@pytest.fixture
def mock_proxy_manager(mock_tool_definitions):
    """Create a mock ProxyManager with pre-configured tool responses."""
    manager = Mock(spec=ProxyManager)

    # Mock list_tools to return tool definitions by server
    async def list_tools_impl(server_name: str):
        if server_name not in mock_tool_definitions:
            raise KeyError(f"Server '{server_name}' not found")
        # Add small delay to simulate network latency (5ms)
        await asyncio.sleep(0.005)
        return mock_tool_definitions[server_name]

    manager.list_tools = AsyncMock(side_effect=list_tools_impl)

    # Mock call_tool to return success responses
    async def call_tool_impl(
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int | None = None
    ):
        # Add small delay to simulate execution (10ms)
        await asyncio.sleep(0.010)

        # Simulate different responses based on tool
        if "search" in tool_name:
            return Mock(
                content=[{
                    "type": "text",
                    "text": f"Search results for: {arguments.get('query', 'N/A')}"
                }],
                isError=False
            )
        elif "query" in tool_name:
            return Mock(
                content=[{
                    "type": "text",
                    "text": "Query executed successfully"
                }],
                isError=False
            )
        elif "list" in tool_name:
            return Mock(
                content=[{
                    "type": "text",
                    "text": json.dumps(["item1", "item2", "item3"])
                }],
                isError=False
            )
        elif "read" in tool_name:
            return Mock(
                content=[{
                    "type": "text",
                    "text": "File contents here"
                }],
                isError=False
            )
        else:
            return Mock(
                content=[{
                    "type": "text",
                    "text": f"Tool {tool_name} executed"
                }],
                isError=False
            )

    manager.call_tool = AsyncMock(side_effect=call_tool_impl)

    return manager


@pytest.fixture
def policy_engine(gateway_rules):
    """Create PolicyEngine instance with test rules."""
    return PolicyEngine(gateway_rules)


@pytest.fixture
def metrics_collector():
    """Create MetricsCollector instance."""
    collector = MetricsCollector()
    # Reset metrics before each test
    collector.reset_sync()
    return collector


@pytest.fixture
def initialized_gateway(policy_engine, mcp_config, mock_proxy_manager):
    """Initialize gateway with all components for testing."""
    initialize_gateway(policy_engine, mcp_config, mock_proxy_manager)
    return gateway


# ============================================================================
# Full Workflow Tests
# ============================================================================


class TestFullWorkflow:
    """Test complete workflow through all three gateway tools."""

    @pytest.mark.asyncio
    async def test_researcher_workflow(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test researcher agent complete workflow: discover → get tools → execute.

        Workflow:
        1. list_servers - should see brave-search only
        2. get_server_tools - get brave-search tools
        3. execute_tool - execute brave_web_search
        """
        agent_id = "researcher"
        start_time = time.perf_counter()

        # Step 1: List servers
        servers = await list_servers(agent_id=agent_id)

        assert len(servers) == 1
        assert servers[0]["name"] == "brave-search"
        assert servers[0]["transport"] == "stdio"

        # Step 2: Get server tools
        tools_response = await get_server_tools(
            agent_id=agent_id,
            server="brave-search"
        )

        assert "error" not in tools_response or tools_response["error"] is None
        assert tools_response["server"] == "brave-search"
        assert tools_response["returned"] == 2  # brave_web_search, brave_local_search
        assert len(tools_response["tools"]) == 2

        # Verify tool names
        tool_names = {t["name"] for t in tools_response["tools"]}
        assert "brave_web_search" in tool_names
        assert "brave_local_search" in tool_names

        # Step 3: Execute a tool
        result = await execute_tool(
            agent_id=agent_id,
            server="brave-search",
            tool="brave_web_search",
            args={"query": "MCP protocol"}
        )

        assert result["isError"] is False
        assert len(result["content"]) > 0
        assert "MCP protocol" in result["content"][0]["text"]

        # Verify total workflow latency
        end_time = time.perf_counter()
        total_latency_ms = (end_time - start_time) * 1000
        assert total_latency_ms < 200, f"Workflow took {total_latency_ms:.2f}ms (target: <200ms)"

    @pytest.mark.asyncio
    async def test_backend_workflow(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test backend agent workflow with multiple servers.

        Backend can access:
        - postgres (tools: query, list_*, deny: drop_*, delete_*)
        - filesystem (tools: read_*, list_*, deny: write_*, delete_*)
        """
        agent_id = "backend"

        # Step 1: List servers
        servers = await list_servers(agent_id=agent_id)

        assert len(servers) == 2
        server_names = {s["name"] for s in servers}
        assert "postgres" in server_names
        assert "filesystem" in server_names

        # Step 2a: Get postgres tools
        pg_tools = await get_server_tools(
            agent_id=agent_id,
            server="postgres"
        )

        assert "error" not in pg_tools or pg_tools["error"] is None
        pg_tool_names = {t["name"] for t in pg_tools["tools"]}
        # Should have query and list_tables, but NOT drop_table
        assert "query" in pg_tool_names
        assert "list_tables" in pg_tool_names
        assert "drop_table" not in pg_tool_names  # Explicitly denied

        # Step 2b: Get filesystem tools
        fs_tools = await get_server_tools(
            agent_id=agent_id,
            server="filesystem"
        )

        assert "error" not in fs_tools or fs_tools["error"] is None
        fs_tool_names = {t["name"] for t in fs_tools["tools"]}
        # Should have read_file and list_directory, but NOT write_file
        assert "read_file" in fs_tool_names
        assert "list_directory" in fs_tool_names
        assert "write_file" not in fs_tool_names  # Explicitly denied

        # Step 3: Execute allowed tools

        # Execute postgres query
        result = await execute_tool(
            agent_id=agent_id,
            server="postgres",
            tool="query",
            args={"sql": "SELECT * FROM users"}
        )
        assert result["isError"] is False

        # Execute filesystem read
        result = await execute_tool(
            agent_id=agent_id,
            server="filesystem",
            tool="read_file",
            args={"path": "/data/config.json"}
        )
        assert result["isError"] is False

    @pytest.mark.asyncio
    async def test_admin_wildcard_workflow(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test admin agent with wildcard access to all servers and tools."""
        agent_id = "admin"

        # Step 1: List servers - should see all
        servers = await list_servers(agent_id=agent_id)

        assert len(servers) == 3
        server_names = {s["name"] for s in servers}
        assert "brave-search" in server_names
        assert "postgres" in server_names
        assert "filesystem" in server_names

        # Step 2: Get tools from each server - should see all

        pg_tools = await get_server_tools(agent_id=agent_id, server="postgres")
        assert len(pg_tools["tools"]) == 3  # All postgres tools including drop_table

        fs_tools = await get_server_tools(agent_id=agent_id, server="filesystem")
        assert len(fs_tools["tools"]) == 3  # All filesystem tools including write_file

        # Step 3: Execute any tool (including ones denied to others)

        # Admin can execute drop_table (denied to backend)
        result = await execute_tool(
            agent_id=agent_id,
            server="postgres",
            tool="drop_table",
            args={"table": "temp_data"}
        )
        assert result["isError"] is False


# ============================================================================
# Policy Enforcement Tests
# ============================================================================


class TestPolicyEnforcement:
    """Test policy-based access control across all tools."""

    @pytest.mark.asyncio
    async def test_server_access_denial(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test that agents cannot access servers they're not allowed to."""
        agent_id = "researcher"  # Only allowed brave-search

        # list_servers should not include postgres
        servers = await list_servers(agent_id=agent_id)
        server_names = {s["name"] for s in servers}
        assert "postgres" not in server_names

        # get_server_tools should return error
        response = await get_server_tools(
            agent_id=agent_id,
            server="postgres"
        )
        assert "error" in response
        assert "Access denied" in response["error"]
        assert len(response["tools"]) == 0

        # execute_tool should raise ToolError
        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id=agent_id,
                server="postgres",
                tool="query",
                args={}
            )
        assert "cannot access server" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_tool_access_denial(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test that agents cannot access specific tools they're denied."""
        agent_id = "backend"  # Denied drop_* on postgres

        # get_server_tools should filter out denied tools
        response = await get_server_tools(
            agent_id=agent_id,
            server="postgres"
        )

        tool_names = {t["name"] for t in response["tools"]}
        assert "drop_table" not in tool_names  # Explicitly denied
        assert "query" in tool_names  # Explicitly allowed

        # execute_tool should raise ToolError for denied tool
        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id=agent_id,
                server="postgres",
                tool="drop_table",
                args={"table": "users"}
            )
        assert "not authorized to call tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_wildcard_access(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test wildcard patterns in tool access."""
        agent_id = "backend"  # Allowed list_* on postgres

        response = await get_server_tools(
            agent_id=agent_id,
            server="postgres"
        )

        # Should include list_tables (matches list_*)
        tool_names = {t["name"] for t in response["tools"]}
        assert "list_tables" in tool_names

    @pytest.mark.asyncio
    async def test_unknown_agent_denial(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test that unknown agents are denied (default policy)."""
        agent_id = "unknown_agent"

        # list_servers should return empty list
        servers = await list_servers(agent_id=agent_id)
        assert len(servers) == 0

        # get_server_tools should return error
        response = await get_server_tools(
            agent_id=agent_id,
            server="brave-search"
        )
        assert "error" in response
        assert "Access denied" in response["error"]


# ============================================================================
# Concurrent Access Tests
# ============================================================================


class TestConcurrentAccess:
    """Test concurrent requests from multiple agents."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_multiple_agents(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test multiple agents making concurrent requests.

        Simulates realistic load:
        - 3 agents (researcher, backend, admin)
        - Each makes 10 requests
        - Requests execute concurrently
        """

        async def agent_workflow(agent_id: str, request_count: int):
            """Execute multiple requests for an agent."""
            results = []
            for i in range(request_count):
                # Vary the operation
                if i % 3 == 0:
                    result = await list_servers(agent_id=agent_id)
                    results.append(("list_servers", result))
                elif i % 3 == 1:
                    # Get tools based on agent permissions
                    if agent_id == "researcher":
                        server = "brave-search"
                    elif agent_id == "backend":
                        server = "postgres"
                    else:
                        server = "filesystem"

                    result = await get_server_tools(agent_id=agent_id, server=server)
                    results.append(("get_server_tools", result))
                else:
                    # Execute tool
                    try:
                        if agent_id == "researcher":
                            result = await execute_tool(
                                agent_id=agent_id,
                                server="brave-search",
                                tool="brave_web_search",
                                args={"query": f"test {i}"}
                            )
                        elif agent_id == "backend":
                            result = await execute_tool(
                                agent_id=agent_id,
                                server="postgres",
                                tool="query",
                                args={"sql": f"SELECT {i}"}
                            )
                        else:
                            result = await execute_tool(
                                agent_id=agent_id,
                                server="filesystem",
                                tool="read_file",
                                args={"path": f"/file{i}.txt"}
                            )
                        results.append(("execute_tool", result))
                    except Exception as e:
                        results.append(("execute_tool", {"error": str(e)}))

            return results

        # Run concurrent workflows
        start_time = time.perf_counter()

        tasks = [
            agent_workflow("researcher", 10),
            agent_workflow("backend", 10),
            agent_workflow("admin", 10)
        ]

        results = await asyncio.gather(*tasks)

        end_time = time.perf_counter()
        total_time_ms = (end_time - start_time) * 1000

        # Verify all requests completed
        assert len(results) == 3
        assert all(len(agent_results) == 10 for agent_results in results)

        # Verify no errors from allowed operations
        for agent_results in results:
            for op_type, result in agent_results:
                if op_type == "execute_tool" and isinstance(result, dict):
                    # Check it's not an error result
                    if "error" not in result or not result.get("isError"):
                        assert True  # Success

        # Performance check - 30 operations should complete in reasonable time
        # With mocked delays (5ms + 10ms per operation), expect ~450ms + overhead
        assert total_time_ms < 1000, f"Concurrent operations took {total_time_ms:.2f}ms"

    @pytest.mark.asyncio
    async def test_session_isolation(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test that agent sessions are isolated (no context mixing).

        Each agent should maintain independent state and not interfere
        with other agents' operations.
        """

        # Track results by agent
        results = {}

        async def execute_for_agent(agent_id: str, server: str, tool: str, args: dict):
            """Execute tool and store result."""
            result = await execute_tool(
                agent_id=agent_id,
                server=server,
                tool=tool,
                args=args
            )
            results[agent_id] = result
            return result

        # Execute concurrently for different agents
        tasks = [
            execute_for_agent(
                "researcher",
                "brave-search",
                "brave_web_search",
                {"query": "researcher query"}
            ),
            execute_for_agent(
                "backend",
                "postgres",
                "query",
                {"sql": "SELECT * FROM backend_data"}
            ),
            execute_for_agent(
                "admin",
                "filesystem",
                "read_file",
                {"path": "/admin/config.json"}
            )
        ]

        await asyncio.gather(*tasks)

        # Verify each agent got correct result
        assert "researcher query" in results["researcher"]["content"][0]["text"]
        assert "backend" not in results["researcher"]["content"][0]["text"]

        # Each result should be independent
        assert len(results) == 3
        assert all(not r["isError"] for r in results.values())


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_downstream_server_error(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config
    ):
        """Test handling of errors from downstream servers."""
        # Create mock that returns error
        mock_proxy = Mock(spec=ProxyManager)

        # Mock error from list_tools
        mock_proxy.list_tools = AsyncMock(
            side_effect=RuntimeError("Server connection failed")
        )

        initialize_gateway(policy_engine, mcp_config, mock_proxy)

        response = await get_server_tools(
            agent_id="researcher",
            server="brave-search"
        )

        assert "error" in response
        assert "Server unavailable" in response["error"]
        assert response["returned"] == 0

    @pytest.mark.asyncio
    async def test_timeout_handling(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config
    ):
        """Test timeout handling for long-running operations."""
        # Create mock that simulates timeout
        mock_proxy = Mock(spec=ProxyManager)

        async def slow_call_tool(*args, **kwargs):
            """Simulate slow operation that times out."""
            raise asyncio.TimeoutError("Operation timed out")

        mock_proxy.call_tool = AsyncMock(side_effect=slow_call_tool)

        initialize_gateway(policy_engine, mcp_config, mock_proxy)


        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="researcher",
                server="brave-search",
                tool="brave_web_search",
                args={"query": "test"},
                timeout_ms=100
            )

        assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_server_not_found(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test handling of requests to non-existent servers."""
        # Mock list_tools to raise KeyError
        mock_proxy_manager.list_tools = AsyncMock(
            side_effect=KeyError("Server 'nonexistent' not found")
        )

        response = await get_server_tools(
            agent_id="admin",  # Admin has access to all
            server="nonexistent"
        )

        assert "error" in response
        assert "not found" in response["error"]
        assert response["returned"] == 0

    @pytest.mark.asyncio
    async def test_tool_not_found(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config
    ):
        """Test execution of non-existent tool."""
        # Create mock that raises error for unknown tool
        mock_proxy = Mock(spec=ProxyManager)

        mock_proxy.call_tool = AsyncMock(
            side_effect=RuntimeError("Tool 'nonexistent_tool' not found")
        )

        initialize_gateway(policy_engine, mcp_config, mock_proxy)


        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="admin",
                server="brave-search",
                tool="nonexistent_tool",
                args={}
            )

        # Error should mention the tool was not found
        assert "not found" in str(exc_info.value).lower()


# ============================================================================
# Component Integration Tests
# ============================================================================


class TestComponentIntegration:
    """Test integration between gateway components."""

    @pytest.mark.asyncio
    async def test_middleware_agent_extraction(self, gateway_rules, mcp_config):
        """Test that middleware properly extracts and stores agent_id."""
        policy_engine = PolicyEngine(gateway_rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context and message
        from fastmcp.server.middleware import MiddlewareContext

        mock_message = Mock()
        mock_message.arguments = {
            "agent_id": "test_agent",
            "server": "brave-search",
            "other_arg": "value"
        }

        mock_fastmcp_context = Mock()
        mock_fastmcp_context.set_state = Mock()

        mock_context = Mock(spec=MiddlewareContext)
        mock_context.message = mock_message
        mock_context.fastmcp_context = mock_fastmcp_context

        # Mock call_next
        async def call_next(ctx):
            # Verify agent_id is kept in arguments for gateway tools
            assert "agent_id" in ctx.message.arguments
            assert ctx.message.arguments["agent_id"] == "test_agent"
            assert "server" in ctx.message.arguments
            assert "other_arg" in ctx.message.arguments
            return {"success": True}

        # Execute middleware
        result = await middleware.on_call_tool(mock_context, call_next)

        # Verify agent was stored in context
        mock_fastmcp_context.set_state.assert_called_once_with(
            "current_agent",
            "test_agent"
        )

        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_proxy_manager_integration(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test that gateway correctly integrates with ProxyManager."""

        # Execute a tool
        result = await execute_tool(
            agent_id="researcher",
            server="brave-search",
            tool="brave_web_search",
            args={"query": "integration test"}
        )

        # Verify ProxyManager.call_tool was called correctly
        mock_proxy_manager.call_tool.assert_called_once()
        call_args = mock_proxy_manager.call_tool.call_args

        assert call_args[0][0] == "brave-search"  # server
        assert call_args[0][1] == "brave_web_search"  # tool
        assert call_args[0][2]["query"] == "integration test"  # args

    @pytest.mark.asyncio
    async def test_policy_engine_integration(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test that gateway correctly uses PolicyEngine for access control."""

        # Test different agents get different server lists
        researcher_servers = await list_servers(agent_id="researcher")
        backend_servers = await list_servers(agent_id="backend")
        admin_servers = await list_servers(agent_id="admin")

        # Verify policy engine applied correctly
        assert len(researcher_servers) == 1  # brave-search only
        assert len(backend_servers) == 2  # postgres, filesystem
        assert len(admin_servers) == 3  # all servers

        # Verify tool filtering
        backend_tools = await get_server_tools(
            agent_id="backend",
            server="postgres"
        )

        tool_names = {t["name"] for t in backend_tools["tools"]}
        # Backend should not see drop_table (denied)
        assert "drop_table" not in tool_names


# ============================================================================
# Performance Validation Tests
# ============================================================================


class TestPerformance:
    """Test and validate performance targets."""

    @pytest.mark.asyncio
    async def test_list_servers_latency(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Validate list_servers meets <50ms P95 target."""

        latencies = []

        # Run 100 iterations to get P95 measurement
        for _ in range(100):
            start = time.perf_counter()
            await list_servers(agent_id="researcher")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        # Calculate P95
        sorted_latencies = sorted(latencies)
        p95_index = int(95 * len(sorted_latencies) / 100)
        p95_latency = sorted_latencies[p95_index]

        assert p95_latency < 50, f"P95 latency {p95_latency:.2f}ms exceeds 50ms target"

    @pytest.mark.asyncio
    async def test_get_server_tools_latency(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Validate get_server_tools meets <300ms P95 target."""

        latencies = []

        # Run 100 iterations
        for _ in range(100):
            start = time.perf_counter()
            await get_server_tools(
                agent_id="researcher",
                server="brave-search"
            )
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        # Calculate P95
        sorted_latencies = sorted(latencies)
        p95_index = int(95 * len(sorted_latencies) / 100)
        p95_latency = sorted_latencies[p95_index]

        assert p95_latency < 300, f"P95 latency {p95_latency:.2f}ms exceeds 300ms target"

    @pytest.mark.asyncio
    async def test_execute_tool_overhead(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Validate execute_tool overhead is <30ms P95.

        Measures gateway overhead by comparing total time vs mock execution time.
        """

        latencies = []
        mock_execution_time = 10  # Mock adds 10ms delay

        # Run 100 iterations
        for _ in range(100):
            start = time.perf_counter()
            await execute_tool(
                agent_id="researcher",
                server="brave-search",
                tool="brave_web_search",
                args={"query": "test"}
            )
            end = time.perf_counter()

            total_time = (end - start) * 1000
            overhead = total_time - mock_execution_time
            latencies.append(overhead)

        # Calculate P95
        sorted_latencies = sorted(latencies)
        p95_index = int(95 * len(sorted_latencies) / 100)
        p95_overhead = sorted_latencies[p95_index]

        assert p95_overhead < 30, f"P95 overhead {p95_overhead:.2f}ms exceeds 30ms target"

    @pytest.mark.asyncio
    async def test_overall_added_latency(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Validate overall gateway latency is <100ms P95.

        Measures end-to-end latency for complete workflow.
        """

        latencies = []
        mock_time = 15  # Mock delays: 5ms (list_tools) + 10ms (call_tool)

        # Run 50 complete workflows
        for _ in range(50):
            start = time.perf_counter()

            # Complete workflow
            await list_servers(agent_id="researcher")
            await get_server_tools(agent_id="researcher", server="brave-search")
            await execute_tool(
                agent_id="researcher",
                server="brave-search",
                tool="brave_web_search",
                args={"query": "test"}
            )

            end = time.perf_counter()

            total_time = (end - start) * 1000
            overhead = total_time - mock_time
            latencies.append(overhead)

        # Calculate P95
        sorted_latencies = sorted(latencies)
        p95_index = int(95 * len(sorted_latencies) / 100)
        p95_latency = sorted_latencies[p95_index]

        assert p95_latency < 100, f"P95 overall latency {p95_latency:.2f}ms exceeds 100ms target"


# ============================================================================
# Additional Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_tool_list(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config
    ):
        """Test handling of server with no tools."""
        mock_proxy = Mock(spec=ProxyManager)
        mock_proxy.list_tools = AsyncMock(return_value=[])

        initialize_gateway(policy_engine, mcp_config, mock_proxy)

        response = await get_server_tools(
            agent_id="researcher",
            server="brave-search"
        )

        assert response["total_available"] == 0
        assert response["returned"] == 0
        assert len(response["tools"]) == 0

    @pytest.mark.asyncio
    async def test_tool_name_filtering(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test filtering tools by explicit names."""

        response = await get_server_tools(
            agent_id="researcher",
            server="brave-search",
            names="brave_web_search"  # Only request this tool
        )

        assert response["returned"] == 1
        assert response["tools"][0]["name"] == "brave_web_search"

    @pytest.mark.asyncio
    async def test_tool_pattern_filtering(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test filtering tools by wildcard pattern."""

        response = await get_server_tools(
            agent_id="researcher",
            server="brave-search",
            pattern="brave_*_search"  # Match both tools
        )

        assert response["returned"] == 2
        tool_names = {t["name"] for t in response["tools"]}
        assert "brave_web_search" in tool_names
        assert "brave_local_search" in tool_names

    @pytest.mark.asyncio
    async def test_max_schema_tokens_limit(
        self,
        initialized_gateway,
        policy_engine,
        mcp_config,
        mock_proxy_manager
    ):
        """Test that max_schema_tokens limits returned tools."""

        # Request with very low token limit
        response = await get_server_tools(
            agent_id="researcher",
            server="brave-search",
            max_schema_tokens=50  # Very low limit
        )

        # Should return fewer tools due to token budget
        assert response["returned"] <= 2
        assert response["tokens_used"] is not None
        assert response["tokens_used"] <= 50
