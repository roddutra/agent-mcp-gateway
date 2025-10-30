"""Gateway server for Agent MCP Gateway."""

import asyncio
import fnmatch
import re
from typing import Any, Optional

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from .policy import PolicyEngine
from .proxy import ProxyManager


# Create FastMCP instance
gateway = FastMCP(name="Agent MCP Gateway")

# Module-level storage for configurations (set by main.py)
_policy_engine: PolicyEngine | None = None
_mcp_config: dict | None = None
_proxy_manager: ProxyManager | None = None
_check_config_changes_fn: Any | None = None  # Fallback reload checker
_get_reload_status_fn: Any | None = None  # Reload status getter for diagnostics


def initialize_gateway(
    policy_engine: PolicyEngine,
    mcp_config: dict,
    proxy_manager: ProxyManager | None = None,
    check_config_changes_fn: Any = None,
    get_reload_status_fn: Any = None
):
    """Initialize gateway with policy engine, MCP config, and proxy manager.

    This must be called before the gateway starts accepting requests.

    Args:
        policy_engine: PolicyEngine instance for access control
        mcp_config: MCP servers configuration dictionary
        proxy_manager: Optional ProxyManager instance (required for get_server_tools)
        check_config_changes_fn: Optional function to check for config changes (fallback mechanism)
        get_reload_status_fn: Optional function to get reload status for diagnostics
    """
    global _policy_engine, _mcp_config, _proxy_manager, _check_config_changes_fn, _get_reload_status_fn
    _policy_engine = policy_engine
    _mcp_config = mcp_config
    _proxy_manager = proxy_manager
    _check_config_changes_fn = check_config_changes_fn
    _get_reload_status_fn = get_reload_status_fn


@gateway.tool
async def list_servers(
    agent_id: str,
    include_metadata: bool = False
) -> list[dict]:
    """List all MCP servers available to the calling agent based on policy rules.

    This tool returns a filtered list of MCP servers that the specified agent
    is allowed to access according to the configured gateway rules. This enables
    agents to discover available servers without loading all tool definitions upfront.

    Args:
        agent_id: Identifier of the agent making the request
        include_metadata: Whether to include extended server metadata (default: False)

    Returns:
        List of server information dicts with:
        - name: Server name
        - transport: "stdio" or "http"
        - description: Server description (if include_metadata=True)

    Example:
        >>> await list_servers("researcher")
        [
            {"name": "brave-search", "transport": "stdio"},
            {"name": "filesystem", "transport": "stdio"}
        ]
    """
    # Get configurations from module-level storage
    policy_engine = _policy_engine
    mcp_config = _mcp_config

    if not policy_engine:
        raise RuntimeError("PolicyEngine not initialized in gateway state")
    if not mcp_config:
        raise RuntimeError("MCP configuration not initialized in gateway state")

    # Get servers this agent can access
    allowed_servers = policy_engine.get_allowed_servers(agent_id)
    all_servers = mcp_config.get("mcpServers", {})

    # Build response
    server_list = []

    # Handle wildcard access
    if allowed_servers == ["*"]:
        # Agent has wildcard access - return all servers
        allowed_servers = list(all_servers.keys())

    for server_name in allowed_servers:
        if server_name in all_servers:
            server_config = all_servers[server_name]

            # Determine transport type
            transport = "stdio" if "command" in server_config else "http"

            server_info = {
                "name": server_name,
                "transport": transport
            }

            # Add metadata if requested
            if include_metadata:
                if "description" in server_config:
                    server_info["description"] = server_config["description"]

                # Add transport-specific metadata
                if transport == "stdio":
                    server_info["command"] = server_config.get("command")
                elif transport == "http":
                    server_info["url"] = server_config.get("url")

            server_list.append(server_info)

    return server_list


def _matches_pattern(tool_name: str, pattern: str) -> bool:
    """Check if tool name matches wildcard pattern.

    Uses glob-style pattern matching:
    - * matches any sequence of characters
    - ? matches any single character
    - [seq] matches any character in seq
    - [!seq] matches any character not in seq

    Args:
        tool_name: Name of the tool to match
        pattern: Pattern with wildcards (e.g., "get_*", "*_user")

    Returns:
        True if tool_name matches pattern, False otherwise

    Example:
        >>> _matches_pattern("get_user", "get_*")
        True
        >>> _matches_pattern("delete_user", "get_*")
        False
        >>> _matches_pattern("list_items", "*_items")
        True
    """
    return fnmatch.fnmatch(tool_name, pattern)


def _estimate_tool_tokens(tool: Any) -> int:
    """Estimate token count for a tool definition.

    Estimates tokens based on name, description, and input schema JSON length.
    Uses rough approximation: characters / 4 = tokens (typical for English text).

    Args:
        tool: Tool object with name, description, and inputSchema attributes

    Returns:
        Estimated token count for the tool definition

    Example:
        >>> tool = Tool(name="get_user", description="Get user by ID", inputSchema={...})
        >>> _estimate_tool_tokens(tool)
        42
    """
    # Count name length
    name_len = len(tool.name) if hasattr(tool, 'name') and tool.name else 0

    # Count description length
    desc_len = len(tool.description) if hasattr(tool, 'description') and tool.description else 0

    # Count input schema length (convert to string for estimation)
    schema_len = 0
    if hasattr(tool, 'inputSchema') and tool.inputSchema:
        # Convert schema dict to string for rough character count
        import json
        try:
            schema_len = len(json.dumps(tool.inputSchema))
        except Exception:
            # If serialization fails, use a default estimate
            schema_len = 100

    # Total characters / 4 = rough token estimate
    total_chars = name_len + desc_len + schema_len
    return max(1, total_chars // 4)


@gateway.tool
async def get_server_tools(
    agent_id: str,
    server: str,
    names: Optional[str] = None,
    pattern: Optional[str] = None,
    max_schema_tokens: Optional[int] = None
) -> dict:
    """Get tool definitions from a server, filtered by agent permissions and optional criteria.

    This tool retrieves available tools from a downstream MCP server, applying
    policy-based filtering, optional name/pattern filters, and token budget limits.
    It enables agents to discover specific tools they need without loading all definitions.

    Args:
        agent_id: Identifier of the agent making the request
        server: Name of the server to query for tools
        names: Optional comma-separated list of tool names (e.g., "tool1,tool2,tool3").
               Leave empty/null for all tools. Single tool name also accepted.
        pattern: Optional wildcard pattern to match tool names (e.g., "get_*", "*_user")
        max_schema_tokens: Optional maximum tokens to return in tool schemas

    Returns:
        Dictionary with:
        - tools: List of tool definition dicts (name, description, inputSchema)
        - server: Server name
        - total_available: Total number of tools on server (before filtering)
        - returned: Number of tools returned after filtering
        - tokens_used: Estimated tokens used (if max_schema_tokens specified)
        - error: Error message if operation failed (e.g., "Access denied", "Server unavailable")

    Examples:
        >>> # Get all tools matching a pattern
        >>> await get_server_tools("researcher", "brave-search", pattern="brave_*")

        >>> # Get specific tools by name
        >>> await get_server_tools("researcher", "brave-search",
        ...                        names="brave_web_search,brave_local_search")
        {
            "tools": [
                {
                    "name": "brave_web_search",
                    "description": "Search the web using Brave",
                    "inputSchema": {...}
                },
                {
                    "name": "brave_local_search",
                    "description": "Search local businesses",
                    "inputSchema": {...}
                }
            ],
            "server": "brave-search",
            "total_available": 10,
            "returned": 2,
            "tokens_used": null
        }
    """
    # Check for config changes (fallback mechanism for when file watching doesn't work)
    if _check_config_changes_fn:
        try:
            _check_config_changes_fn()
        except Exception:
            pass  # Don't let config check errors break tool execution

    # Parse comma-separated names string into list
    names_list: Optional[list[str]] = None
    if names is not None and names.strip():
        # Split by comma and trim whitespace from each name
        names_list = [name.strip() for name in names.split(",") if name.strip()]
        # If we ended up with an empty list after filtering, treat as None
        if not names_list:
            names_list = None

    # Get configurations from module-level storage
    policy_engine = _policy_engine
    proxy_manager = _proxy_manager

    if not policy_engine:
        return {
            "tools": [],
            "server": server,
            "total_available": 0,
            "returned": 0,
            "tokens_used": None,
            "error": "PolicyEngine not initialized in gateway state"
        }

    if not proxy_manager:
        return {
            "tools": [],
            "server": server,
            "total_available": 0,
            "returned": 0,
            "tokens_used": None,
            "error": "ProxyManager not initialized in gateway state"
        }

    # Validate agent can access server
    if not policy_engine.can_access_server(agent_id, server):
        return {
            "tools": [],
            "server": server,
            "total_available": 0,
            "returned": 0,
            "tokens_used": None,
            "error": f"Access denied: Agent '{agent_id}' cannot access server '{server}'"
        }

    # Get tools from downstream server
    try:
        all_tools = await proxy_manager.list_tools(server)
    except KeyError:
        return {
            "tools": [],
            "server": server,
            "total_available": 0,
            "returned": 0,
            "tokens_used": None,
            "error": f"Server '{server}' not found in configured servers"
        }
    except RuntimeError as e:
        return {
            "tools": [],
            "server": server,
            "total_available": 0,
            "returned": 0,
            "tokens_used": None,
            "error": f"Server unavailable: {str(e)}"
        }
    except Exception as e:
        return {
            "tools": [],
            "server": server,
            "total_available": 0,
            "returned": 0,
            "tokens_used": None,
            "error": f"Failed to retrieve tools: {str(e)}"
        }

    total_available = len(all_tools)

    # Filter tools based on criteria
    filtered_tools = []
    token_count = 0

    for tool in all_tools:
        tool_name = tool.name if hasattr(tool, 'name') else str(tool)

        # Filter by explicit names list
        if names_list is not None and tool_name not in names_list:
            continue

        # Filter by wildcard pattern
        if pattern is not None and not _matches_pattern(tool_name, pattern):
            continue

        # Filter by policy permissions
        if not policy_engine.can_access_tool(agent_id, server, tool_name):
            continue

        # Check token budget limit
        if max_schema_tokens is not None:
            tool_tokens = _estimate_tool_tokens(tool)
            if token_count + tool_tokens > max_schema_tokens:
                # Stop adding tools - budget exceeded
                break
            token_count += tool_tokens

        # Convert tool to dictionary format
        tool_dict = {
            "name": tool_name,
            "description": tool.description if hasattr(tool, 'description') and tool.description else "",
            "inputSchema": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
        }

        filtered_tools.append(tool_dict)

    return {
        "tools": filtered_tools,
        "server": server,
        "total_available": total_available,
        "returned": len(filtered_tools),
        "tokens_used": token_count if max_schema_tokens is not None else None
    }


async def _execute_tool_impl(
    agent_id: str,
    server: str,
    tool: str,
    args: dict,
    timeout_ms: Optional[int] = None
) -> dict:
    """Execute a tool on a downstream MCP server with policy-based access control.

    This tool proxies tool execution requests to downstream MCP servers after
    validating that the agent has permission to access both the server and the
    specific tool. It transparently forwards the result from the downstream server,
    including any error flags.

    Args:
        agent_id: Identifier of the agent making the request
        server: Name of the server where the tool is located
        tool: Name of the tool to execute
        args: Arguments to pass to the tool (as dictionary)
        timeout_ms: Optional timeout in milliseconds for tool execution

    Returns:
        Dictionary with:
        - content: List of content blocks from the tool execution
        - isError: Boolean indicating if the result represents an error

    Raises:
        ToolError: If access is denied, server is unavailable, timeout occurs,
                  or tool execution fails

    Example:
        >>> await execute_tool(
        ...     "researcher",
        ...     "brave-search",
        ...     "brave_web_search",
        ...     {"query": "MCP protocol"},
        ...     timeout_ms=5000
        ... )
        {
            "content": [
                {
                    "type": "text",
                    "text": "Search results: ..."
                }
            ],
            "isError": False
        }
    """
    # Get configurations from module-level storage
    policy_engine = _policy_engine
    proxy_manager = _proxy_manager

    if not policy_engine:
        raise ToolError("PolicyEngine not initialized in gateway state")

    if not proxy_manager:
        raise ToolError("ProxyManager not initialized in gateway state")

    # 1. Validate agent can access server
    if not policy_engine.can_access_server(agent_id, server):
        raise ToolError(f"Agent '{agent_id}' cannot access server '{server}'")

    # 2. Validate agent can access tool
    if not policy_engine.can_access_tool(agent_id, server, tool):
        raise ToolError(f"Agent '{agent_id}' not authorized to call tool '{tool}' on server '{server}'")

    # 3. Execute tool on downstream server
    try:
        result = await proxy_manager.call_tool(server, tool, args, timeout_ms)

        # 4. Return result transparently
        # Handle both ToolResult objects and dict responses
        if hasattr(result, 'content'):
            # ToolResult object
            return {
                "content": result.content,
                "isError": getattr(result, "isError", False)
            }
        elif isinstance(result, dict):
            # Already a dict - ensure it has the expected structure
            return {
                "content": result.get("content", [{"type": "text", "text": str(result)}]),
                "isError": result.get("isError", False)
            }
        else:
            # Wrap other return types
            return {
                "content": [{"type": "text", "text": str(result)}],
                "isError": False
            }

    except asyncio.TimeoutError:
        raise ToolError(f"Tool execution timed out after {timeout_ms}ms")
    except KeyError as e:
        # Server not found
        raise ToolError(f"Server '{server}' not found in configured servers")
    except RuntimeError as e:
        # Server unavailable or tool execution failed
        error_msg = str(e)
        if "not found" in error_msg.lower() or "unavailable" in error_msg.lower():
            raise ToolError(error_msg)
        else:
            raise ToolError(f"Tool execution failed: {error_msg}")
    except Exception as e:
        # Other errors
        raise ToolError(f"Tool execution failed: {str(e)}")


# Register the tool with FastMCP
execute_tool = gateway.tool(_execute_tool_impl)


@gateway.tool
async def get_gateway_status(agent_id: str) -> dict:
    """Get comprehensive gateway status and diagnostics.

    This tool provides visibility into gateway health and configuration state,
    including hot reload status, policy engine state, and available servers.
    Useful for debugging configuration issues and verifying that config changes
    have been applied successfully.

    Args:
        agent_id: Identifier of the calling agent (required for all gateway tools)

    Returns:
        Dictionary containing:
        - reload_status: Hot reload attempt/success timestamps, errors, and warnings
          for both mcp_config and gateway_rules files
        - policy_state: Current PolicyEngine configuration (agent count, defaults)
        - available_servers: List of configured MCP server names
        - config_paths: Paths to configuration files
        - message: Human-readable status message

    Example:
        >>> await get_gateway_status("researcher")
        {
            "reload_status": {
                "mcp_config": {
                    "last_attempt": "2025-01-15T10:30:00",
                    "last_success": "2025-01-15T10:30:00",
                    "last_error": None,
                    "attempt_count": 3,
                    "success_count": 3
                },
                "gateway_rules": {
                    "last_attempt": "2025-01-15T10:35:00",
                    "last_success": "2025-01-15T10:35:00",
                    "last_error": None,
                    "attempt_count": 2,
                    "success_count": 2,
                    "last_warnings": []
                }
            },
            "policy_state": {
                "total_agents": 3,
                "agent_ids": ["researcher", "backend", "admin"],
                "defaults": {"deny_on_missing_agent": True}
            },
            "available_servers": ["brave-search", "postgres", "filesystem"],
            "config_paths": {
                "mcp_config": "/path/to/.mcp.json",
                "gateway_rules": "/path/to/gateway-rules.json"
            },
            "message": "Gateway is operational. Check reload_status for hot reload health."
        }
    """
    # Get reload status if available
    reload_status = None
    if _get_reload_status_fn:
        try:
            reload_status = _get_reload_status_fn()
            # Convert datetime objects to ISO strings for JSON serialization
            if reload_status:
                for config_type in ["mcp_config", "gateway_rules"]:
                    if config_type in reload_status:
                        for key in ["last_attempt", "last_success"]:
                            if reload_status[config_type].get(key):
                                reload_status[config_type][key] = reload_status[config_type][key].isoformat()
        except Exception:
            reload_status = {"error": "Failed to retrieve reload status"}

    # Get PolicyEngine state
    policy_state = {}
    if _policy_engine:
        try:
            policy_state = {
                "total_agents": len(_policy_engine.agents),
                "agent_ids": list(_policy_engine.agents.keys()),
                "defaults": _policy_engine.defaults,
            }
        except Exception:
            policy_state = {"error": "Failed to retrieve policy state"}

    # Get available servers
    available_servers = []
    if _mcp_config and "mcpServers" in _mcp_config:
        available_servers = list(_mcp_config["mcpServers"].keys())

    # Get config file paths from src/config.py
    config_paths = {}
    try:
        from src.config import get_stored_config_paths
        mcp_path, rules_path = get_stored_config_paths()
        config_paths = {
            "mcp_config": mcp_path,
            "gateway_rules": rules_path,
        }
    except Exception:
        config_paths = {"error": "Failed to retrieve config paths"}

    return {
        "reload_status": reload_status,
        "policy_state": policy_state,
        "available_servers": available_servers,
        "config_paths": config_paths,
        "message": "Gateway is operational. Check reload_status for hot reload health."
    }
