"""Unit tests for access control middleware.

Tests the AgentAccessControl middleware that enforces per-agent access
rules by extracting agent identity, validating permissions, and managing
context state.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from dataclasses import dataclass
from typing import Any

from src.middleware import AgentAccessControl
from src.policy import PolicyEngine
from fastmcp.exceptions import ToolError


# Mock classes to simulate FastMCP middleware context

@dataclass
class MockToolCall:
    """Mock tool call message."""
    name: str
    arguments: dict[str, Any]


@dataclass
class MockMiddlewareContext:
    """Mock middleware context."""
    message: MockToolCall
    fastmcp_context: Any = None
    method: str = "tools/call"


class MockFastMCPContext:
    """Mock FastMCP context with state management."""

    def __init__(self):
        self._state = {}

    def set_state(self, key: str, value: Any):
        """Store state value."""
        self._state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        """Retrieve state value."""
        return self._state.get(key, default)


class TestMiddlewareAgentExtraction:
    """Test agent_id extraction and context storage."""

    @pytest.mark.asyncio
    async def test_middleware_extracts_agent_id(self):
        """Test that middleware successfully extracts agent_id from arguments."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context with agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"agent_id": "test_agent", "include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"result": "success"})

        # Execute middleware
        result = await middleware.on_call_tool(context, call_next)

        # Verify agent was stored in context
        assert fastmcp_ctx.get_state("current_agent") == "test_agent"
        assert result == {"result": "success"}
        assert call_next.called

    @pytest.mark.asyncio
    async def test_middleware_keeps_agent_id(self):
        """Test that middleware keeps agent_id in arguments for gateway tools."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context with multiple arguments
        tool_call = MockToolCall(
            name="list_servers",
            arguments={
                "agent_id": "test_agent",
                "include_metadata": True,
                "format": "json"
            }
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"result": "success"})

        # Execute middleware
        await middleware.on_call_tool(context, call_next)

        # Verify agent_id is kept (gateway tools need it) along with other arguments
        assert "agent_id" in tool_call.arguments
        assert tool_call.arguments["agent_id"] == "test_agent"
        assert tool_call.arguments["include_metadata"] is True
        assert tool_call.arguments["format"] == "json"

    @pytest.mark.asyncio
    async def test_middleware_stores_in_context(self):
        """Test that middleware stores agent in context state."""
        rules = {
            "agents": {
                "researcher": {
                    "allow": {"servers": ["brave-search"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context
        tool_call = MockToolCall(
            name="get_server_tools",
            arguments={"agent_id": "researcher", "server": "brave-search"}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"tools": []})

        # Execute middleware
        await middleware.on_call_tool(context, call_next)

        # Verify context state was updated
        stored_agent = fastmcp_ctx.get_state("current_agent")
        assert stored_agent == "researcher"


class TestMiddlewareMissingAgentID:
    """Test handling of missing agent_id based on default policy."""

    @pytest.mark.asyncio
    async def test_middleware_missing_agent_id_deny(self):
        """Test that missing agent_id raises error when default policy denies."""
        rules = {
            "agents": {
                "known_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock()

        # Execute middleware - should raise ToolError
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(context, call_next)

        # Verify error message
        assert "agent_id" in str(exc_info.value).lower()
        assert "missing" in str(exc_info.value).lower()

        # Verify call_next was NOT called
        assert not call_next.called

    @pytest.mark.asyncio
    async def test_middleware_missing_agent_id_allow(self):
        """Test that missing agent_id uses fallback when default policy permits.

        NOTE: This test was updated from the original implementation. Previously,
        missing agent_id with deny_on_missing_agent=false would proceed with None.
        Now it attempts to use fallback chain (GATEWAY_DEFAULT_AGENT or 'default' agent).
        Since no fallback is configured in this test, it should error with helpful message.
        """
        rules = {
            "agents": {
                "known_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id (and no fallback configured)
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock()

        # Execute middleware - should raise error explaining fallback options
        # This is the new behavior: we need a fallback agent configured
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(context, call_next)

        # Verify error message is helpful
        error_msg = str(exc_info.value).lower()
        assert "agent_id" in error_msg or "default" in error_msg or "gateway_default_agent" in error_msg
        assert not call_next.called


class TestMiddlewareGatewayTools:
    """Test that gateway tools are allowed through middleware."""

    @pytest.mark.asyncio
    async def test_middleware_gateway_tools_allowed(self):
        """Test that gateway tools pass through middleware without blocking."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Test each gateway tool
        gateway_tools = ["list_servers", "get_server_tools", "execute_tool"]

        for tool_name in gateway_tools:
            tool_call = MockToolCall(
                name=tool_name,
                arguments={"agent_id": "test_agent", "server": "api"}
            )
            fastmcp_ctx = MockFastMCPContext()
            context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

            # Mock call_next
            call_next = AsyncMock(return_value={"result": "ok"})

            # Execute middleware
            result = await middleware.on_call_tool(context, call_next)

            # Verify tool was allowed through
            assert result == {"result": "ok"}
            assert call_next.called
            assert fastmcp_ctx.get_state("current_agent") == "test_agent"

    @pytest.mark.asyncio
    async def test_middleware_list_tools_no_filtering(self):
        """Test that on_list_tools passes through without filtering."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context (list_tools has no message arguments)
        context = MockMiddlewareContext(
            message=MockToolCall(name="", arguments={}),
            fastmcp_context=MockFastMCPContext()
        )
        context.method = "tools/list"

        # Mock call_next with a list of tools
        mock_tools = [
            {"name": "list_servers", "description": "List servers"},
            {"name": "get_server_tools", "description": "Get tools"},
            {"name": "execute_tool", "description": "Execute tool"}
        ]
        call_next = AsyncMock(return_value=mock_tools)

        # Execute middleware
        result = await middleware.on_list_tools(context, call_next)

        # Verify no filtering occurred
        assert result == mock_tools
        assert len(result) == 3
        assert call_next.called


class TestMiddlewareWithoutFastMCPContext:
    """Test middleware behavior when fastmcp_context is None."""

    @pytest.mark.asyncio
    async def test_middleware_without_context_object(self):
        """Test that middleware handles missing fastmcp_context gracefully."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT fastmcp_context
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"agent_id": "test_agent"}
        )
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=None)

        # Mock call_next
        call_next = AsyncMock(return_value={"result": "success"})

        # Execute middleware - should not crash
        result = await middleware.on_call_tool(context, call_next)

        # Verify execution proceeded despite no context
        assert result == {"result": "success"}
        assert call_next.called


class TestMiddlewareEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_middleware_empty_arguments(self):
        """Test middleware with empty arguments dict."""
        rules = {
            "agents": {},
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context with empty arguments
        tool_call = MockToolCall(name="list_servers", arguments={})
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock()

        # Execute middleware - should raise ToolError for missing agent_id
        with pytest.raises(ToolError):
            await middleware.on_call_tool(context, call_next)

    @pytest.mark.asyncio
    async def test_middleware_none_arguments(self):
        """Test middleware when arguments is None."""
        rules = {
            "agents": {},
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context with None arguments
        tool_call = MockToolCall(name="list_servers", arguments=None)
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock()

        # Execute middleware - should handle None arguments gracefully
        with pytest.raises(ToolError):
            await middleware.on_call_tool(context, call_next)

    @pytest.mark.asyncio
    async def test_middleware_agent_id_with_special_characters(self):
        """Test that agent_id with special characters is handled correctly."""
        rules = {
            "agents": {
                "agent-with-dashes_123": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context with special character agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"agent_id": "agent-with-dashes_123", "foo": "bar"}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"result": "ok"})

        # Execute middleware
        result = await middleware.on_call_tool(context, call_next)

        # Verify agent was stored correctly
        assert fastmcp_ctx.get_state("current_agent") == "agent-with-dashes_123"
        assert result == {"result": "ok"}
        # agent_id is kept in arguments for gateway tools
        assert "agent_id" in tool_call.arguments
        assert tool_call.arguments["agent_id"] == "agent-with-dashes_123"
        assert "foo" in tool_call.arguments


class TestMiddlewareMultipleArguments:
    """Test middleware with various argument combinations."""

    @pytest.mark.asyncio
    async def test_middleware_preserves_all_arguments(self):
        """Test that all arguments including agent_id are preserved."""
        rules = {
            "agents": {
                "test": {"allow": {"servers": ["*"]}}
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context with many arguments
        original_args = {
            "agent_id": "test",
            "server": "postgres",
            "tool": "query",
            "args": {"sql": "SELECT * FROM users"},
            "timeout_ms": 5000,
            "format": "json"
        }
        tool_call = MockToolCall(name="execute_tool", arguments=original_args.copy())
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"rows": []})

        # Execute middleware
        await middleware.on_call_tool(context, call_next)

        # Verify all arguments are preserved (including agent_id)
        assert "agent_id" in tool_call.arguments
        assert tool_call.arguments["agent_id"] == "test"
        assert tool_call.arguments["server"] == "postgres"
        assert tool_call.arguments["tool"] == "query"
        assert tool_call.arguments["args"] == {"sql": "SELECT * FROM users"}
        assert tool_call.arguments["timeout_ms"] == 5000
        assert tool_call.arguments["format"] == "json"

    @pytest.mark.asyncio
    async def test_middleware_agent_id_only_argument(self):
        """Test when agent_id is the only argument."""
        rules = {
            "agents": {
                "solo": {"allow": {"servers": ["api"]}}
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context with only agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"agent_id": "solo"}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"servers": []})

        # Execute middleware
        await middleware.on_call_tool(context, call_next)

        # Verify agent_id is still present
        assert tool_call.arguments == {"agent_id": "solo"}
        assert fastmcp_ctx.get_state("current_agent") == "solo"


class TestMiddlewareAgentIDFallback:
    """Test agent_id fallback chain when agent_id is missing."""

    @pytest.mark.asyncio
    async def test_fallback_to_env_var(self, monkeypatch):
        """When agent_id missing, should use GATEWAY_DEFAULT_AGENT env var."""
        # Mock get_default_agent_id to return "researcher"
        from src import gateway
        monkeypatch.setattr(gateway, "_default_agent_id", "researcher")

        rules = {
            "agents": {
                "researcher": {
                    "allow": {"servers": ["brave-search"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"servers": ["brave-search"]})

        # Execute middleware - should use researcher's permissions
        result = await middleware.on_call_tool(context, call_next)

        # Verify call succeeded using fallback agent
        assert result == {"servers": ["brave-search"]}
        assert call_next.called
        # Verify context state was set to fallback agent
        assert fastmcp_ctx.get_state("current_agent") == "researcher"

    @pytest.mark.asyncio
    async def test_fallback_to_default_agent(self):
        """When agent_id missing and no env var, should use 'default' agent."""
        rules = {
            "agents": {
                "default": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id (and no env var)
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"servers": ["api"]})

        # Execute middleware - should use default agent's permissions
        result = await middleware.on_call_tool(context, call_next)

        # Verify call succeeded using default agent
        assert result == {"servers": ["api"]}
        assert call_next.called
        # Verify context state was set to default agent
        assert fastmcp_ctx.get_state("current_agent") == "default"

    @pytest.mark.asyncio
    async def test_env_var_precedence_over_default(self, monkeypatch):
        """GATEWAY_DEFAULT_AGENT should override 'default' agent in rules."""
        # Mock get_default_agent_id to return "researcher"
        from src import gateway
        monkeypatch.setattr(gateway, "_default_agent_id", "researcher")

        rules = {
            "agents": {
                "researcher": {
                    "allow": {"servers": ["brave-search"]}
                },
                "default": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"servers": ["brave-search"]})

        # Execute middleware
        await middleware.on_call_tool(context, call_next)

        # Verify used researcher (not default)
        assert fastmcp_ctx.get_state("current_agent") == "researcher"
        assert call_next.called

    @pytest.mark.asyncio
    async def test_fallback_agent_not_in_rules(self, monkeypatch):
        """Should error if fallback agent doesn't exist in rules config."""
        # Mock get_default_agent_id to return nonexistent agent
        from src import gateway
        monkeypatch.setattr(gateway, "_default_agent_id", "nonexistent")

        rules = {
            "agents": {
                "researcher": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock()

        # Execute middleware - should raise helpful error
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(context, call_next)

        # Verify error message is helpful
        error_msg = str(exc_info.value)
        assert "nonexistent" in error_msg.lower() or "fallback" in error_msg.lower() or "default" in error_msg.lower()
        assert not call_next.called

    @pytest.mark.asyncio
    async def test_no_fallback_configured(self):
        """Should error if no env var and no 'default' agent."""
        rules = {
            "agents": {
                "researcher": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id (and no env var, no default agent)
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock()

        # Execute middleware - should raise error explaining config options
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(context, call_next)

        # Verify error message explains configuration options
        error_msg = str(exc_info.value).lower()
        assert "agent_id" in error_msg or "default" in error_msg or "gateway_default_agent" in error_msg
        assert not call_next.called

    @pytest.mark.asyncio
    async def test_deny_on_missing_bypasses_fallback(self, monkeypatch):
        """When deny_on_missing_agent=true, should reject without checking fallback."""
        # Mock get_default_agent_id to return valid agent
        from src import gateway
        monkeypatch.setattr(gateway, "_default_agent_id", "researcher")

        rules = {
            "agents": {
                "researcher": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock()

        # Execute middleware - should raise error immediately (doesn't use env var)
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(context, call_next)

        # Verify error about missing agent_id
        error_msg = str(exc_info.value)
        assert "agent_id" in error_msg.lower()
        assert "missing" in error_msg.lower()
        assert not call_next.called

    @pytest.mark.asyncio
    async def test_explicit_agent_id_overrides_fallback(self, monkeypatch):
        """When agent_id is provided, fallback should not be used."""
        # Mock get_default_agent_id - but it should be ignored
        from src import gateway
        monkeypatch.setattr(gateway, "_default_agent_id", "researcher")

        rules = {
            "agents": {
                "researcher": {
                    "allow": {"servers": ["brave-search"]}
                },
                "backend": {
                    "allow": {"servers": ["postgres"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITH explicit agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"agent_id": "backend", "include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"servers": ["postgres"]})

        # Execute middleware
        await middleware.on_call_tool(context, call_next)

        # Verify used explicit agent_id (backend), not fallback (researcher)
        assert fastmcp_ctx.get_state("current_agent") == "backend"
        assert call_next.called

    @pytest.mark.asyncio
    async def test_fallback_with_special_characters(self, monkeypatch):
        """Test fallback with agent name containing special characters."""
        # Mock get_default_agent_id with dashes and underscores
        from src import gateway
        monkeypatch.setattr(gateway, "_default_agent_id", "team-backend_v2")

        rules = {
            "agents": {
                "team-backend_v2": {
                    "allow": {"servers": ["postgres"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"servers": ["postgres"]})

        # Execute middleware
        await middleware.on_call_tool(context, call_next)

        # Verify fallback agent with special chars was used
        assert fastmcp_ctx.get_state("current_agent") == "team-backend_v2"
        assert call_next.called

    @pytest.mark.asyncio
    async def test_fallback_empty_env_var_treated_as_unset(self, monkeypatch):
        """Empty GATEWAY_DEFAULT_AGENT env var should fall back to 'default' agent."""
        # Mock get_default_agent_id to return None (empty string evaluates to False)
        from src import gateway
        monkeypatch.setattr(gateway, "_default_agent_id", None)

        rules = {
            "agents": {
                "default": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        policy_engine = PolicyEngine(rules)
        middleware = AgentAccessControl(policy_engine)

        # Create mock context WITHOUT agent_id
        tool_call = MockToolCall(
            name="list_servers",
            arguments={"include_metadata": False}
        )
        fastmcp_ctx = MockFastMCPContext()
        context = MockMiddlewareContext(message=tool_call, fastmcp_context=fastmcp_ctx)

        # Mock call_next
        call_next = AsyncMock(return_value={"servers": ["api"]})

        # Execute middleware - should fall back to 'default' agent
        await middleware.on_call_tool(context, call_next)

        # Verify used 'default' agent (not empty string)
        assert fastmcp_ctx.get_state("current_agent") == "default"
        assert call_next.called
