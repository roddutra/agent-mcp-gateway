"""Gateway server for Agent MCP Gateway."""

import asyncio
import fnmatch
from typing import Annotated, Any, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field
from .policy import PolicyEngine
from .proxy import ProxyManager


# Output schemas for gateway tools
class ServerInfo(BaseModel):
    """Server information returned by list_servers."""
    name: Annotated[str, Field(description="Server name (use in get_server_tools and execute_tool)")]
    description: Annotated[Optional[str], Field(description="What this server provides (from config or null if not configured)")] = None
    transport: Annotated[Optional[str], Field(description="How server communicates: stdio or http (only if include_metadata=true)")] = None
    command: Annotated[Optional[str], Field(description="Command that runs this server (only if include_metadata=true and transport=stdio)")] = None
    url: Annotated[Optional[str], Field(description="Server endpoint (only if include_metadata=true and transport=http)")] = None


class ToolDefinition(BaseModel):
    """Tool definition from downstream server."""
    name: Annotated[str, Field(description="Tool name (use in execute_tool)")]
    description: Annotated[str, Field(description="What this tool does")]
    inputSchema: Annotated[dict, Field(description="JSON Schema defining required/optional parameters for execute_tool args")]


class GetServerToolsResponse(BaseModel):
    """Response from get_server_tools."""
    tools: Annotated[list[ToolDefinition], Field(description="Tool definitions you can access")]
    server: Annotated[str, Field(description="Queried server name")]
    total_available: Annotated[int, Field(description="Total tools on server (may exceed returned if filtered by permissions/criteria)")]
    returned: Annotated[int, Field(description="Count of tools returned (less than total_available is normal due to filtering)")]
    tokens_used: Annotated[Optional[int], Field(description="Tokens used in schemas (if max_schema_tokens was set)")] = None
    error: Annotated[Optional[str], Field(description="Error message if request failed")] = None


class ToolExecutionResponse(BaseModel):
    """Response from execute_tool."""
    content: Annotated[list[dict], Field(description="Result from the downstream tool (format varies by tool)")]
    isError: Annotated[bool, Field(description="True if the downstream tool returned an error")]


class GatewayStatusResponse(BaseModel):
    """Response from get_gateway_status (debug tool)."""
    reload_status: Annotated[Optional[dict], Field(description="Hot reload history with timestamps and errors")]
    policy_state: Annotated[dict, Field(description="Policy engine configuration (agent count, defaults)")]
    available_servers: Annotated[list[str], Field(description="All configured server names")]
    config_paths: Annotated[dict, Field(description="File paths to gateway configuration")]
    message: Annotated[str, Field(description="Summary status message")]


# Create FastMCP instance
gateway = FastMCP(name="Agent MCP Gateway")

# Module-level storage for configurations (set by main.py)
_policy_engine: PolicyEngine | None = None
_mcp_config: dict | None = None
_proxy_manager: ProxyManager | None = None
_check_config_changes_fn: Any | None = None  # Fallback reload checker
_get_reload_status_fn: Any | None = None  # Reload status getter for diagnostics
_default_agent_id: str | None = None  # Default agent for fallback chain
_debug_mode: bool = False  # Debug mode flag


def initialize_gateway(
    policy_engine: PolicyEngine,
    mcp_config: dict,
    proxy_manager: ProxyManager | None = None,
    check_config_changes_fn: Any = None,
    get_reload_status_fn: Any = None,
    default_agent_id: str | None = None,
    debug_mode: bool = False
):
    """Initialize gateway with policy engine, MCP config, and proxy manager.

    This must be called before the gateway starts accepting requests.

    Args:
        policy_engine: PolicyEngine instance for access control
        mcp_config: MCP servers configuration dictionary
        proxy_manager: Optional ProxyManager instance (required for get_server_tools)
        check_config_changes_fn: Optional function to check for config changes (fallback mechanism)
        get_reload_status_fn: Optional function to get reload status for diagnostics
        default_agent_id: Optional default agent ID from GATEWAY_DEFAULT_AGENT env var for fallback chain
        debug_mode: Whether debug mode is enabled (exposes get_gateway_status tool)
    """
    global _policy_engine, _mcp_config, _proxy_manager, _check_config_changes_fn, _get_reload_status_fn, _default_agent_id, _debug_mode
    _policy_engine = policy_engine
    _mcp_config = mcp_config
    _proxy_manager = proxy_manager
    _check_config_changes_fn = check_config_changes_fn
    _get_reload_status_fn = get_reload_status_fn
    _default_agent_id = default_agent_id
    _debug_mode = debug_mode

    # Conditionally register debug tools based on debug mode
    if debug_mode:
        _register_debug_tools()


def get_default_agent_id() -> str | None:
    """Get the default agent ID from gateway configuration.

    Returns:
        Default agent ID from GATEWAY_DEFAULT_AGENT env var, or None if not set
    """
    return _default_agent_id


def _register_debug_tools():
    """Register debug-only tools when debug mode is enabled.

    This function is called by initialize_gateway() when debug_mode=True.
    It registers additional diagnostic tools that should only be available
    in debug/development environments.
    """
    # Register get_gateway_status tool
    # Note: The function itself is always defined (for testing), but only
    # registered as a gateway tool when debug mode is enabled
    gateway.tool(get_gateway_status)


@gateway.tool
async def list_servers(
    agent_id: Annotated[Optional[str], "Your agent identifier (leave empty if not provided to you)"] = None,
    include_metadata: Annotated[bool, "Include technical details (transport, command, url)"] = False
) -> list[dict]:
    """Discover downstream MCP servers available through this gateway. Your access is determined by gateway policy rules. Workflow: 1) Call list_servers to discover servers, 2) Call get_server_tools to see available tools, 3) Call execute_tool to use them."""
    # Defensive check (middleware should have resolved agent_id)
    if agent_id is None:
        raise ToolError("Internal error: agent_id not resolved by middleware")

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

            # Build ServerInfo object - always include name and description
            server_info_kwargs = {
                "name": server_name,
                "description": server_config.get("description")  # Include description always (None if not in config)
            }

            # Add technical metadata if requested
            if include_metadata:
                server_info_kwargs["transport"] = transport

                # Add transport-specific metadata
                if transport == "stdio":
                    server_info_kwargs["command"] = server_config.get("command")
                elif transport == "http":
                    server_info_kwargs["url"] = server_config.get("url")

            server_list.append(ServerInfo(**server_info_kwargs))

    return [server.model_dump() for server in server_list]


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
    agent_id: Annotated[Optional[str], "Your agent identifier (leave empty if not provided to you)"] = None,
    server: Annotated[str, "Server name from list_servers"] = "",
    names: Annotated[Optional[str], "Filter: comma-separated tool names"] = None,
    pattern: Annotated[Optional[str], "Filter: wildcard pattern (e.g., 'get_*')"] = None,
    max_schema_tokens: Annotated[Optional[int], "Limit total tokens in returned schemas"] = None
) -> dict:
    """Discover tools available on a downstream MCP server accessed through this gateway. Returns only tools you have permission to use (filtered by policy rules). Use the returned tool definitions to call execute_tool."""
    # Defensive check (middleware should have resolved agent_id)
    if agent_id is None:
        raise ToolError("Internal error: agent_id not resolved by middleware")

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
        return GetServerToolsResponse(
            tools=[],
            server=server,
            total_available=0,
            returned=0,
            tokens_used=None,
            error="PolicyEngine not initialized in gateway state"
        ).model_dump()

    if not proxy_manager:
        return GetServerToolsResponse(
            tools=[],
            server=server,
            total_available=0,
            returned=0,
            tokens_used=None,
            error="ProxyManager not initialized in gateway state"
        ).model_dump()

    # Validate agent can access server
    if not policy_engine.can_access_server(agent_id, server):
        return GetServerToolsResponse(
            tools=[],
            server=server,
            total_available=0,
            returned=0,
            tokens_used=None,
            error=f"Access denied: Agent '{agent_id}' cannot access server '{server}'"
        ).model_dump()

    # Get tools from downstream server
    try:
        all_tools = await proxy_manager.list_tools(server)
    except KeyError:
        return GetServerToolsResponse(
            tools=[],
            server=server,
            total_available=0,
            returned=0,
            tokens_used=None,
            error=f"Server '{server}' not found in configured servers"
        ).model_dump()
    except RuntimeError as e:
        return GetServerToolsResponse(
            tools=[],
            server=server,
            total_available=0,
            returned=0,
            tokens_used=None,
            error=f"Server unavailable: {str(e)}"
        ).model_dump()
    except Exception as e:
        return GetServerToolsResponse(
            tools=[],
            server=server,
            total_available=0,
            returned=0,
            tokens_used=None,
            error=f"Failed to retrieve tools: {str(e)}"
        ).model_dump()

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

        # Convert tool to ToolDefinition
        tool_definition = ToolDefinition(
            name=tool_name,
            description=tool.description if hasattr(tool, 'description') and tool.description else "",
            inputSchema=tool.inputSchema if hasattr(tool, 'inputSchema') else {}
        )

        filtered_tools.append(tool_definition)

    return GetServerToolsResponse(
        tools=filtered_tools,
        server=server,
        total_available=total_available,
        returned=len(filtered_tools),
        tokens_used=token_count if max_schema_tokens is not None else None
    ).model_dump()


@gateway.tool
async def execute_tool(
    agent_id: Annotated[Optional[str], "Your agent identifier (leave empty if not provided to you)"] = None,
    server: Annotated[str, "Server name from list_servers"] = "",
    tool: Annotated[str, "Tool name from get_server_tools"] = "",
    args: Annotated[dict, "Arguments matching tool's inputSchema"] = {},
    timeout_ms: Annotated[Optional[int], "Execution timeout in milliseconds"] = None
) -> dict:
    """Execute a tool on a downstream MCP server accessed through this gateway. Gateway validates permissions then forwards your request to the server. Returns the server's response directly."""
    # Defensive check (middleware should have resolved agent_id)
    if agent_id is None:
        raise ToolError("Internal error: agent_id not resolved by middleware")

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
            return ToolExecutionResponse(
                content=result.content,
                isError=getattr(result, "isError", False)
            ).model_dump()
        elif isinstance(result, dict):
            # Already a dict - ensure it has the expected structure
            return ToolExecutionResponse(
                content=result.get("content", [{"type": "text", "text": str(result)}]),
                isError=result.get("isError", False)
            ).model_dump()
        else:
            # Wrap other return types
            return ToolExecutionResponse(
                content=[{"type": "text", "text": str(result)}],
                isError=False
            ).model_dump()

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


async def get_gateway_status(
    agent_id: Annotated[Optional[str], "Your agent identifier (leave empty if not provided to you)"] = None
) -> dict:
    """Get gateway status, configuration state, and hot reload diagnostics.

    NOTE: Only available when debug mode is enabled."""
    # Defensive check (middleware should have resolved agent_id)
    if agent_id is None:
        raise ToolError("Internal error: agent_id not resolved by middleware")

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

    return GatewayStatusResponse(
        reload_status=reload_status,
        policy_state=policy_state,
        available_servers=available_servers,
        config_paths=config_paths,
        message="Gateway is operational. Check reload_status for hot reload health."
    ).model_dump()
