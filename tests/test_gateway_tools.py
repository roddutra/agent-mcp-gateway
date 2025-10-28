"""Unit tests for gateway tools (execute_tool)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock

from src.gateway import gateway, initialize_gateway, _execute_tool_impl as execute_tool
from src.policy import PolicyEngine
from src.proxy import ProxyManager
from fastmcp.exceptions import ToolError


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
    manager.call_tool = AsyncMock(return_value=Mock(content=[], isError=False))
    return manager


class TestExecuteTool:
    """Test cases for execute_tool."""

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, mock_policy_engine, mock_proxy_manager):
        """Test successful tool execution."""
        # Mock successful tool result
        mock_result = Mock()
        mock_result.content = [{"type": "text", "text": "Search results"}]
        mock_result.isError = False
        mock_proxy_manager.call_tool = AsyncMock(return_value=mock_result)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await execute_tool(
            agent_id="test_agent",
            server="test_server",
            tool="test_tool",
            args={"query": "test"}
        )

        assert result["content"] == [{"type": "text", "text": "Search results"}]
        assert result["isError"] is False
        mock_proxy_manager.call_tool.assert_called_once_with(
            "test_server",
            "test_tool",
            {"query": "test"},
            None
        )

    @pytest.mark.asyncio
    async def test_execute_tool_denied_server(self, mock_proxy_manager):
        """Test execute_tool when agent cannot access server."""
        # Create policy that denies server access
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=False)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="test_agent",
                server="denied_server",
                tool="test_tool",
                args={}
            )

        assert "cannot access server" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_denied_tool(self, mock_proxy_manager):
        """Test execute_tool when agent cannot access specific tool."""
        # Create policy that allows server but denies tool
        mock_policy_engine = Mock(spec=PolicyEngine)
        mock_policy_engine.can_access_server = Mock(return_value=True)
        mock_policy_engine.can_access_tool = Mock(return_value=False)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="test_agent",
                server="test_server",
                tool="denied_tool",
                args={}
            )

        assert "not authorized to call tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_timeout(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool timeout handling."""
        mock_proxy_manager.call_tool = AsyncMock(side_effect=asyncio.TimeoutError())

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="test_agent",
                server="test_server",
                tool="slow_tool",
                args={},
                timeout_ms=1000
            )

        assert "timed out" in str(exc_info.value)
        assert "1000ms" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_downstream_error(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool when downstream server returns error."""
        # Mock error result
        mock_result = Mock()
        mock_result.content = [{"type": "text", "text": "Error: Invalid query"}]
        mock_result.isError = True
        mock_proxy_manager.call_tool = AsyncMock(return_value=mock_result)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await execute_tool(
            agent_id="test_agent",
            server="test_server",
            tool="test_tool",
            args={"sql": "INVALID"}
        )

        assert result["isError"] is True
        assert result["content"] == [{"type": "text", "text": "Error: Invalid query"}]

    @pytest.mark.asyncio
    async def test_execute_tool_result_forwarding(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool preserves content and isError from downstream."""
        # Mock result with complex content
        mock_result = Mock()
        mock_result.content = [
            {"type": "text", "text": "Result 1"},
            {"type": "text", "text": "Result 2"}
        ]
        mock_result.isError = False
        mock_proxy_manager.call_tool = AsyncMock(return_value=mock_result)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await execute_tool(
            agent_id="test_agent",
            server="test_server",
            tool="test_tool",
            args={}
        )

        assert len(result["content"]) == 2
        assert result["content"][0]["text"] == "Result 1"
        assert result["content"][1]["text"] == "Result 2"
        assert result["isError"] is False

    @pytest.mark.asyncio
    async def test_execute_tool_server_not_found(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool when server doesn't exist."""
        mock_proxy_manager.call_tool = AsyncMock(side_effect=KeyError("Server not found"))

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="test_agent",
                server="nonexistent_server",
                tool="test_tool",
                args={}
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_with_timeout_parameter(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool passes timeout_ms to proxy manager."""
        mock_result = Mock()
        mock_result.content = [{"type": "text", "text": "Success"}]
        mock_result.isError = False
        mock_proxy_manager.call_tool = AsyncMock(return_value=mock_result)

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await execute_tool(
            agent_id="test_agent",
            server="test_server",
            tool="test_tool",
            args={},
            timeout_ms=5000
        )

        assert result["isError"] is False
        mock_proxy_manager.call_tool.assert_called_once_with(
            "test_server",
            "test_tool",
            {},
            5000
        )

    @pytest.mark.asyncio
    async def test_execute_tool_runtime_error(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool when downstream raises RuntimeError."""
        mock_proxy_manager.call_tool = AsyncMock(
            side_effect=RuntimeError("Connection failed")
        )

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="test_agent",
                server="test_server",
                tool="test_tool",
                args={}
            )

        assert "Tool execution failed" in str(exc_info.value)
        assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_dict_result(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool handles dict results from proxy manager."""
        # Some proxy managers might return dicts instead of ToolResult objects
        mock_proxy_manager.call_tool = AsyncMock(return_value={
            "content": [{"type": "text", "text": "Dict result"}],
            "isError": False
        })

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await execute_tool(
            agent_id="test_agent",
            server="test_server",
            tool="test_tool",
            args={}
        )

        assert result["content"] == [{"type": "text", "text": "Dict result"}]
        assert result["isError"] is False

    @pytest.mark.asyncio
    async def test_execute_tool_non_standard_result(self, mock_policy_engine, mock_proxy_manager):
        """Test execute_tool wraps non-standard result types."""
        # Handle cases where proxy manager returns unexpected types
        mock_proxy_manager.call_tool = AsyncMock(return_value="Simple string result")

        initialize_gateway(mock_policy_engine, {}, mock_proxy_manager)

        result = await execute_tool(
            agent_id="test_agent",
            server="test_server",
            tool="test_tool",
            args={}
        )

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "Simple string result" in result["content"][0]["text"]
        assert result["isError"] is False

    @pytest.mark.asyncio
    async def test_execute_tool_policy_engine_not_initialized(self, mock_proxy_manager):
        """Test execute_tool when PolicyEngine not initialized."""
        # Initialize with None policy engine
        initialize_gateway(None, {}, mock_proxy_manager)

        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="test_agent",
                server="test_server",
                tool="test_tool",
                args={}
            )

        assert "PolicyEngine not initialized" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_proxy_manager_not_initialized(self, mock_policy_engine):
        """Test execute_tool when ProxyManager not initialized."""
        # Initialize with None proxy manager
        initialize_gateway(mock_policy_engine, {}, None)

        with pytest.raises(ToolError) as exc_info:
            await execute_tool(
                agent_id="test_agent",
                server="test_server",
                tool="test_tool",
                args={}
            )

        assert "ProxyManager not initialized" in str(exc_info.value)
