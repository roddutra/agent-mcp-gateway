"""Unit tests for get_server_tools gateway tool.

This module tests the get_server_tools gateway tool, which enables agents to
discover and retrieve filtered tool definitions from downstream MCP servers.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from src.gateway import initialize_gateway, get_server_tools as get_server_tools_tool, _matches_pattern, _estimate_tool_tokens
from src.policy import PolicyEngine
from src.proxy import ProxyManager

# Extract the actual function from FastMCP's FunctionTool wrapper
get_server_tools = get_server_tools_tool.fn


# Mock tool class to simulate FastMCP Tool objects
class MockTool:
    """Mock tool object for testing."""

    def __init__(self, name: str, description: str = "", inputSchema: dict | None = None):
        self.name = name
        self.description = description
        self.inputSchema = inputSchema or {}


@pytest.fixture
def mock_policy_engine():
    """Create a mock PolicyEngine for testing."""
    engine = Mock(spec=PolicyEngine)
    engine.can_access_server = Mock(return_value=True)
    engine.can_access_tool = Mock(return_value=True)
    return engine


@pytest.fixture
def mock_proxy_manager():
    """Create a mock ProxyManager for testing."""
    manager = Mock(spec=ProxyManager)
    manager.list_tools = AsyncMock(return_value=[])
    return manager


@pytest.fixture
def sample_tools():
    """Create sample tool objects for testing."""
    return [
        MockTool(
            name="get_user",
            description="Get user by ID",
            inputSchema={"type": "object", "properties": {"id": {"type": "string"}}}
        ),
        MockTool(
            name="get_users",
            description="List all users",
            inputSchema={"type": "object", "properties": {"limit": {"type": "integer"}}}
        ),
        MockTool(
            name="create_user",
            description="Create a new user",
            inputSchema={"type": "object", "properties": {"name": {"type": "string"}}}
        ),
        MockTool(
            name="delete_user",
            description="Delete a user",
            inputSchema={"type": "object", "properties": {"id": {"type": "string"}}}
        ),
        MockTool(
            name="update_user",
            description="Update user details",
            inputSchema={"type": "object", "properties": {"id": {"type": "string"}}}
        ),
    ]


class TestMatchesPattern:
    """Test cases for _matches_pattern helper function."""

    def test_exact_match(self):
        """Test exact pattern matching."""
        assert _matches_pattern("get_user", "get_user") is True
        assert _matches_pattern("get_user", "get_users") is False

    def test_wildcard_star(self):
        """Test * wildcard matching."""
        assert _matches_pattern("get_user", "get_*") is True
        assert _matches_pattern("get_users", "get_*") is True
        assert _matches_pattern("create_user", "get_*") is False

    def test_wildcard_star_suffix(self):
        """Test * wildcard as suffix."""
        assert _matches_pattern("list_users", "*_users") is True
        assert _matches_pattern("get_users", "*_users") is True
        assert _matches_pattern("users_list", "*_users") is False

    def test_wildcard_star_middle(self):
        """Test * wildcard in middle."""
        assert _matches_pattern("get_user_by_id", "get_*_id") is True
        assert _matches_pattern("get_item_by_id", "get_*_id") is True
        assert _matches_pattern("get_user_name", "get_*_id") is False

    def test_wildcard_question_mark(self):
        """Test ? wildcard matching."""
        assert _matches_pattern("get1", "get?") is True
        assert _matches_pattern("get2", "get?") is True
        assert _matches_pattern("get12", "get?") is False
        assert _matches_pattern("get", "get?") is False

    def test_wildcard_character_set(self):
        """Test character set matching."""
        assert _matches_pattern("get1", "get[123]") is True
        assert _matches_pattern("get2", "get[123]") is True
        assert _matches_pattern("get4", "get[123]") is False

    def test_wildcard_negated_character_set(self):
        """Test negated character set matching."""
        assert _matches_pattern("geta", "get[!123]") is True
        assert _matches_pattern("get1", "get[!123]") is False

    def test_match_all_pattern(self):
        """Test * matches everything."""
        assert _matches_pattern("anything", "*") is True
        assert _matches_pattern("", "*") is True
        assert _matches_pattern("some_long_tool_name", "*") is True


class TestEstimateToolTokens:
    """Test cases for _estimate_tool_tokens helper function."""

    def test_estimate_simple_tool(self):
        """Test token estimation for simple tool."""
        tool = MockTool(
            name="get_user",
            description="Get user by ID",
            inputSchema={"type": "object"}
        )
        tokens = _estimate_tool_tokens(tool)
        # name (8) + description (15) + schema (~20) = ~43 chars / 4 = ~10 tokens
        assert tokens > 0
        assert tokens < 100  # Should be reasonable

    def test_estimate_tool_without_description(self):
        """Test token estimation for tool without description."""
        tool = MockTool(
            name="simple",
            description="",
            inputSchema={"type": "object"}
        )
        tokens = _estimate_tool_tokens(tool)
        assert tokens > 0

    def test_estimate_tool_with_large_schema(self):
        """Test token estimation for tool with large schema."""
        large_schema = {
            "type": "object",
            "properties": {
                f"field{i}": {"type": "string", "description": f"Field {i}"}
                for i in range(20)
            }
        }
        tool = MockTool(
            name="complex_tool",
            description="A tool with many parameters",
            inputSchema=large_schema
        )
        tokens = _estimate_tool_tokens(tool)
        # Large schema should result in more tokens
        assert tokens > 50

    def test_estimate_tool_minimum_tokens(self):
        """Test that minimum tokens is 1."""
        tool = MockTool(name="x", description="", inputSchema={})
        tokens = _estimate_tool_tokens(tool)
        assert tokens >= 1

    def test_estimate_tool_without_name(self):
        """Test token estimation when tool has no name attribute."""
        tool = Mock()
        tool.name = None
        tool.description = "Some description"
        tool.inputSchema = {"type": "object"}
        tokens = _estimate_tool_tokens(tool)
        assert tokens > 0


class TestGetServerToolsBasic:
    """Test cases for basic get_server_tools functionality."""

    @pytest.mark.asyncio
    async def test_get_server_tools_basic(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test basic get_server_tools functionality."""
        # Setup
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        # Execute
        result = await get_server_tools(agent_id="test_agent", server="test_server")

        # Verify
        assert "tools" in result
        assert "server" in result
        assert "total_available" in result
        assert "returned" in result
        assert "tokens_used" in result

        assert result["server"] == "test_server"
        assert result["total_available"] == 5
        assert result["returned"] == 5
        assert result["tokens_used"] is None  # Not requested
        assert len(result["tools"]) == 5

        # Verify tool structure
        first_tool = result["tools"][0]
        assert "name" in first_tool
        assert "description" in first_tool
        assert "inputSchema" in first_tool
        assert first_tool["name"] == "get_user"

    @pytest.mark.asyncio
    async def test_get_server_tools_empty_server(self, mock_policy_engine, mock_proxy_manager):
        """Test get_server_tools with server that has no tools."""
        # Setup
        mock_proxy_manager.list_tools = AsyncMock(return_value=[])
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        # Execute
        result = await get_server_tools(agent_id="test_agent", server="empty_server")

        # Verify
        assert result["total_available"] == 0
        assert result["returned"] == 0
        assert len(result["tools"]) == 0

    @pytest.mark.asyncio
    async def test_get_server_tools_not_initialized(self):
        """Test get_server_tools when gateway not initialized."""
        # Don't initialize gateway
        initialize_gateway(None, {}, None)

        # Execute
        result = await get_server_tools(agent_id="test_agent", server="test_server")

        # Verify error response
        assert "error" in result
        assert "PolicyEngine not initialized" in result["error"]
        assert result["returned"] == 0

    @pytest.mark.asyncio
    async def test_get_server_tools_proxy_manager_not_initialized(self, mock_policy_engine):
        """Test get_server_tools when ProxyManager not initialized."""
        initialize_gateway(mock_policy_engine, {}, None)

        # Execute
        result = await get_server_tools(agent_id="test_agent", server="test_server")

        # Verify error response
        assert "error" in result
        assert "ProxyManager not initialized" in result["error"]
        assert result["returned"] == 0


class TestGetServerToolsFilterByNames:
    """Test cases for filtering tools by explicit names."""

    @pytest.mark.asyncio
    async def test_filter_by_single_name(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test filtering by a single tool name."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            names="get_user"
        )

        assert result["total_available"] == 5
        assert result["returned"] == 1
        assert len(result["tools"]) == 1
        assert result["tools"][0]["name"] == "get_user"

    @pytest.mark.asyncio
    async def test_filter_by_multiple_names(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test filtering by multiple comma-separated tool names."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            names="get_user,create_user"
        )

        assert result["total_available"] == 5
        assert result["returned"] == 2
        assert len(result["tools"]) == 2
        tool_names = [t["name"] for t in result["tools"]]
        assert "get_user" in tool_names
        assert "create_user" in tool_names

    @pytest.mark.asyncio
    async def test_filter_by_nonexistent_name(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test filtering by tool name that doesn't exist."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            names="nonexistent_tool"
        )

        assert result["total_available"] == 5
        assert result["returned"] == 0
        assert len(result["tools"]) == 0

    @pytest.mark.asyncio
    async def test_filter_by_names_preserves_order(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test that filtering by names preserves server order, not request order."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        # Request in different order than they appear on server
        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            names="delete_user,get_user"
        )

        assert result["returned"] == 2
        # Should return in server order (get_user before delete_user)
        assert result["tools"][0]["name"] == "get_user"
        assert result["tools"][1]["name"] == "delete_user"


class TestGetServerToolsFilterByPattern:
    """Test cases for filtering tools by wildcard patterns."""

    @pytest.mark.asyncio
    async def test_filter_by_prefix_pattern(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test filtering by prefix pattern (get_*)."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            pattern="get_*"
        )

        assert result["total_available"] == 5
        assert result["returned"] == 2
        tool_names = [t["name"] for t in result["tools"]]
        assert "get_user" in tool_names
        assert "get_users" in tool_names
        assert "create_user" not in tool_names

    @pytest.mark.asyncio
    async def test_filter_by_suffix_pattern(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test filtering by suffix pattern (*_user)."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            pattern="*_user"
        )

        assert result["total_available"] == 5
        # Should match: get_user, create_user, delete_user, update_user (not get_users)
        assert result["returned"] == 4
        tool_names = [t["name"] for t in result["tools"]]
        assert "get_user" in tool_names
        assert "create_user" in tool_names
        assert "delete_user" in tool_names
        assert "update_user" in tool_names
        assert "get_users" not in tool_names

    @pytest.mark.asyncio
    async def test_filter_by_wildcard_all(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test filtering by wildcard all (*)."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            pattern="*"
        )

        assert result["total_available"] == 5
        assert result["returned"] == 5

    @pytest.mark.asyncio
    async def test_filter_by_pattern_no_matches(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test filtering by pattern that matches no tools."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            pattern="admin_*"
        )

        assert result["total_available"] == 5
        assert result["returned"] == 0
        assert len(result["tools"]) == 0


class TestGetServerToolsPolicyEnforcement:
    """Test cases for policy-based access control."""

    @pytest.mark.asyncio
    async def test_policy_filters_denied_tools(self, mock_proxy_manager, sample_tools):
        """Test that policy engine filters out denied tools."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)

        # Create policy that denies delete_user
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=True)

        def can_access_tool(agent_id, server, tool):
            # Deny delete_user
            return tool != "delete_user"

        mock_policy_engine.can_access_tool = Mock(side_effect=can_access_tool)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="test_server")

        assert result["total_available"] == 5
        assert result["returned"] == 4  # One tool denied
        tool_names = [t["name"] for t in result["tools"]]
        assert "delete_user" not in tool_names

    @pytest.mark.asyncio
    async def test_policy_denies_all_tools(self, mock_proxy_manager, sample_tools):
        """Test when policy denies all tools."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)

        # Create policy that denies all tools
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=True)
        mock_policy_engine.can_access_tool = Mock(return_value=False)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="test_server")

        assert result["total_available"] == 5
        assert result["returned"] == 0
        assert len(result["tools"]) == 0

    @pytest.mark.asyncio
    async def test_policy_allows_only_read_tools(self, mock_proxy_manager, sample_tools):
        """Test policy that allows only read operations."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)

        # Create policy that allows only get_* tools
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=True)

        def can_access_tool(agent_id, server, tool):
            return tool.startswith("get_")

        mock_policy_engine.can_access_tool = Mock(side_effect=can_access_tool)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="test_server")

        assert result["total_available"] == 5
        assert result["returned"] == 2
        tool_names = [t["name"] for t in result["tools"]]
        assert "get_user" in tool_names
        assert "get_users" in tool_names


class TestGetServerToolsTokenBudget:
    """Test cases for token budget limiting."""

    @pytest.mark.asyncio
    async def test_token_budget_limits_results(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test that max_schema_tokens limits number of tools returned."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        # Request with very small token budget
        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            max_schema_tokens=50
        )

        assert result["total_available"] == 5
        # Should return fewer tools due to token budget
        assert result["returned"] < 5
        assert result["tokens_used"] is not None
        assert result["tokens_used"] <= 50

    @pytest.mark.asyncio
    async def test_token_budget_reports_usage(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test that tokens_used is reported when max_schema_tokens specified."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            max_schema_tokens=500
        )

        assert result["tokens_used"] is not None
        assert result["tokens_used"] > 0
        assert result["tokens_used"] <= 500

    @pytest.mark.asyncio
    async def test_no_token_budget_returns_all(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test that without token budget, all matching tools are returned."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="test_server")

        assert result["returned"] == 5
        assert result["tokens_used"] is None

    @pytest.mark.asyncio
    async def test_token_budget_zero_returns_empty(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test that token budget of 0 returns no tools."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            max_schema_tokens=0
        )

        assert result["returned"] == 0
        assert result["tokens_used"] == 0


class TestGetServerToolsAccessDenied:
    """Test cases for access denied scenarios."""

    @pytest.mark.asyncio
    async def test_denied_server_access(self, mock_proxy_manager):
        """Test error when agent cannot access server."""
        # Create policy that denies server access
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=False)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="denied_server")

        assert "error" in result
        assert "Access denied" in result["error"]
        assert "denied_server" in result["error"]
        assert result["returned"] == 0
        assert len(result["tools"]) == 0

    @pytest.mark.asyncio
    async def test_unknown_agent_denied(self, mock_proxy_manager):
        """Test that unknown agents are denied access."""
        # Create policy with deny_on_missing_agent=True
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=False)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="unknown_agent", server="test_server")

        assert "error" in result
        assert "Access denied" in result["error"]


class TestGetServerToolsServerNotFound:
    """Test cases for non-existent servers."""

    @pytest.mark.asyncio
    async def test_server_not_found(self, mock_policy_engine):
        """Test error when server doesn't exist."""
        # Create proxy manager that raises KeyError
        mock_proxy_manager = Mock(spec=ProxyManager)
        mock_proxy_manager.list_tools = AsyncMock(side_effect=KeyError("Server not found"))

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="nonexistent_server")

        assert "error" in result
        assert "not found" in result["error"]
        assert result["returned"] == 0


class TestGetServerToolsConnectionError:
    """Test cases for downstream server connection errors."""

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_policy_engine):
        """Test error when downstream server is unreachable."""
        # Create proxy manager that raises RuntimeError
        mock_proxy_manager = Mock(spec=ProxyManager)
        mock_proxy_manager.list_tools = AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="unreachable_server")

        assert "error" in result
        assert "Server unavailable" in result["error"]
        assert result["returned"] == 0

    @pytest.mark.asyncio
    async def test_generic_exception(self, mock_policy_engine):
        """Test handling of unexpected exceptions."""
        # Create proxy manager that raises generic exception
        mock_proxy_manager = Mock(spec=ProxyManager)
        mock_proxy_manager.list_tools = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(agent_id="test_agent", server="error_server")

        assert "error" in result
        assert "Failed to retrieve tools" in result["error"]
        assert result["returned"] == 0


class TestGetServerToolsCombinedFilters:
    """Test cases for combining multiple filters."""

    @pytest.mark.asyncio
    async def test_names_and_pattern_combined(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test combining names filter with pattern filter."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        # Request get_user and create_user, but pattern only matches get_*
        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            names="get_user,create_user",
            pattern="get_*"
        )

        # Should only return get_user (matches both filters)
        assert result["returned"] == 1
        assert result["tools"][0]["name"] == "get_user"

    @pytest.mark.asyncio
    async def test_pattern_and_policy_combined(self, mock_proxy_manager, sample_tools):
        """Test combining pattern filter with policy filter."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)

        # Create policy that denies get_users
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=True)

        def can_access_tool(agent_id, server, tool):
            return tool != "get_users"

        mock_policy_engine.can_access_tool = Mock(side_effect=can_access_tool)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        # Request with get_* pattern
        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            pattern="get_*"
        )

        # Should return only get_user (get_users denied by policy)
        assert result["returned"] == 1
        assert result["tools"][0]["name"] == "get_user"

    @pytest.mark.asyncio
    async def test_all_filters_combined(self, mock_proxy_manager, sample_tools):
        """Test combining all filters: names, pattern, policy, and token budget."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)

        # Create policy that denies delete_user
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=True)

        def can_access_tool(agent_id, server, tool):
            return tool != "delete_user"

        mock_policy_engine.can_access_tool = Mock(side_effect=can_access_tool)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        # Request with all filters
        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            names="get_user,delete_user,update_user",
            pattern="*_user",
            max_schema_tokens=50
        )

        # delete_user should be filtered out by policy
        # Remaining tools limited by token budget
        assert result["returned"] <= 2  # get_user and update_user, limited by budget
        tool_names = [t["name"] for t in result["tools"]]
        assert "delete_user" not in tool_names
        assert result["tokens_used"] is not None
        assert result["tokens_used"] <= 50

    @pytest.mark.asyncio
    async def test_names_string_empty(self, mock_policy_engine, mock_proxy_manager, sample_tools):
        """Test that empty names string returns all tools (no filter)."""
        mock_proxy_manager.list_tools = AsyncMock(return_value=sample_tools)
        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await get_server_tools(
            agent_id="test_agent",
            server="test_server",
            names=""
        )

        # Empty string means no filter - should return all tools
        assert result["returned"] == 5
        assert len(result["tools"]) == 5
