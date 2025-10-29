"""Test that get_server_tools reflects policy changes after hot reload.

This test verifies that when gateway rules are reloaded via PolicyEngine.reload(),
the get_server_tools function immediately reflects the new policy rules.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from src.gateway import initialize_gateway, get_server_tools as get_server_tools_tool
from src.policy import PolicyEngine
from src.proxy import ProxyManager

# Extract the actual function from FastMCP's FunctionTool wrapper
get_server_tools = get_server_tools_tool.fn


class MockTool:
    """Mock tool object."""
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.inputSchema = {"type": "object"}


@pytest.mark.asyncio
async def test_get_server_tools_reflects_policy_reload():
    """Test that get_server_tools immediately reflects policy changes after reload.

    This is a regression test for the reported bug where modifying gateway-rules.json
    to deny a tool didn't prevent that tool from being returned by get_server_tools.

    Flow:
    1. Initialize with rules that deny brave_local_search only
    2. Call get_server_tools - should return brave_video_search (not denied)
    3. Reload rules to also deny brave_video_search
    4. Call get_server_tools again - should NOT return brave_video_search
    """

    # Initial rules - only brave_local_search denied
    initial_rules = {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search"],
                    "tools": {
                        "brave-search": ["*"]  # Allow all
                    }
                },
                "deny": {
                    "tools": {
                        "brave-search": ["brave_local_search"]  # Only local denied
                    }
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": True
        }
    }

    # Create PolicyEngine with initial rules
    policy_engine = PolicyEngine(initial_rules)

    # Create mock ProxyManager that returns mock tools
    mock_proxy = Mock(spec=ProxyManager)
    async def mock_list_tools(server):
        return [
            MockTool("brave_web_search"),
            MockTool("brave_local_search"),
            MockTool("brave_video_search"),
            MockTool("brave_news_search"),
        ]
    mock_proxy.list_tools = mock_list_tools

    # Initialize gateway
    mcp_config = {
        "mcpServers": {
            "brave-search": {"command": "npx", "args": ["-y", "test"]}
        }
    }
    initialize_gateway(policy_engine, mcp_config, mock_proxy)

    # Test 1: Initial state - brave_video_search should be returned
    result1 = await get_server_tools("researcher", "brave-search")
    tool_names1 = [t['name'] for t in result1['tools']]

    assert "brave_local_search" not in tool_names1, \
        "brave_local_search should be denied initially"
    assert "brave_video_search" in tool_names1, \
        "brave_video_search should be allowed initially"
    assert "brave_web_search" in tool_names1, \
        "brave_web_search should be allowed"
    assert "brave_news_search" in tool_names1, \
        "brave_news_search should be allowed"

    # Reload rules to ALSO deny brave_video_search
    modified_rules = {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search"],
                    "tools": {
                        "brave-search": ["*"]  # Allow all
                    }
                },
                "deny": {
                    "tools": {
                        "brave-search": ["brave_local_search", "brave_video_search"]  # Both denied
                    }
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": True
        }
    }

    success, error = policy_engine.reload(modified_rules)
    assert success is True, f"Reload should succeed, but got error: {error}"

    # Test 2: After reload - brave_video_search should NOT be returned
    result2 = await get_server_tools("researcher", "brave-search")
    tool_names2 = [t['name'] for t in result2['tools']]

    assert "brave_local_search" not in tool_names2, \
        "brave_local_search should still be denied after reload"
    assert "brave_video_search" not in tool_names2, \
        "BUG: brave_video_search should be denied after reload"
    assert "brave_web_search" in tool_names2, \
        "brave_web_search should still be allowed"
    assert "brave_news_search" in tool_names2, \
        "brave_news_search should still be allowed"

    # Verify directly with policy engine
    can_access_video = policy_engine.can_access_tool(
        "researcher", "brave-search", "brave_video_search"
    )
    assert can_access_video is False, \
        "PolicyEngine should report brave_video_search as denied"


@pytest.mark.asyncio
async def test_get_server_tools_reflects_policy_allow_after_reload():
    """Test that get_server_tools reflects when a tool is re-allowed after being denied.

    This tests the opposite direction - removing a deny rule should make the tool
    available again.
    """

    # Initial rules - brave_video_search denied
    initial_rules = {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search"],
                    "tools": {
                        "brave-search": ["*"]
                    }
                },
                "deny": {
                    "tools": {
                        "brave-search": ["brave_video_search"]  # Video denied initially
                    }
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": True
        }
    }

    policy_engine = PolicyEngine(initial_rules)

    # Mock ProxyManager
    mock_proxy = Mock(spec=ProxyManager)
    async def mock_list_tools(server):
        return [
            MockTool("brave_web_search"),
            MockTool("brave_video_search"),
        ]
    mock_proxy.list_tools = mock_list_tools

    # Initialize gateway
    mcp_config = {
        "mcpServers": {
            "brave-search": {"command": "npx"}
        }
    }
    initialize_gateway(policy_engine, mcp_config, mock_proxy)

    # Test 1: brave_video_search should be denied initially
    result1 = await get_server_tools("researcher", "brave-search")
    tool_names1 = [t['name'] for t in result1['tools']]

    assert "brave_video_search" not in tool_names1, \
        "brave_video_search should be denied initially"
    assert "brave_web_search" in tool_names1

    # Reload rules to REMOVE the deny (allow video_search now)
    modified_rules = {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search"],
                    "tools": {
                        "brave-search": ["*"]
                    }
                },
                "deny": {
                    "tools": {
                        "brave-search": []  # Empty deny list
                    }
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": True
        }
    }

    success, error = policy_engine.reload(modified_rules)
    assert success is True

    # Test 2: brave_video_search should now be allowed
    result2 = await get_server_tools("researcher", "brave-search")
    tool_names2 = [t['name'] for t in result2['tools']]

    assert "brave_video_search" in tool_names2, \
        "brave_video_search should be allowed after removing deny rule"
    assert "brave_web_search" in tool_names2
