"""Gateway server for Agent MCP Gateway."""

from fastmcp import FastMCP, Context
from .policy import PolicyEngine


# Create FastMCP instance
gateway = FastMCP(name="Agent MCP Gateway")

# Module-level storage for configurations (set by main.py)
_policy_engine: PolicyEngine | None = None
_mcp_config: dict | None = None


def initialize_gateway(policy_engine: PolicyEngine, mcp_config: dict):
    """Initialize gateway with policy engine and MCP config.

    This must be called before the gateway starts accepting requests.
    """
    global _policy_engine, _mcp_config
    _policy_engine = policy_engine
    _mcp_config = mcp_config


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
