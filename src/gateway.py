"""Gateway server for Agent MCP Gateway."""

import asyncio
import fnmatch
import re
from typing import Any

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


def initialize_gateway(
    policy_engine: PolicyEngine,
    mcp_config: dict,
    proxy_manager: ProxyManager | None = None
):
    """Initialize gateway with policy engine, MCP config, and proxy manager.

    This must be called before the gateway starts accepting requests.

    Args:
        policy_engine: PolicyEngine instance for access control
        mcp_config: MCP servers configuration dictionary
        proxy_manager: Optional ProxyManager instance (required for get_server_tools)
    """
    global _policy_engine, _mcp_config, _proxy_manager
    _policy_engine = policy_engine
    _mcp_config = mcp_config
    _proxy_manager = proxy_manager


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
    names: list[str] | None = None,
    pattern: str | None = None,
    max_schema_tokens: int | None = None
) -> dict:
    """Get tool definitions from a server, filtered by agent permissions and optional criteria.

    This tool retrieves available tools from a downstream MCP server, applying
    policy-based filtering, optional name/pattern filters, and token budget limits.
    It enables agents to discover specific tools they need without loading all definitions.

    Args:
        agent_id: Identifier of the agent making the request
        server: Name of the server to query for tools
        names: Optional list of specific tool names to retrieve
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

    Example:
        >>> await get_server_tools("researcher", "brave-search", pattern="brave_*")
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
            "tokens_used": 450
        }
    """
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
        if names is not None and tool_name not in names:
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
    timeout_ms: int | None = None
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
