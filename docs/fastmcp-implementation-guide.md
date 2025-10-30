# FastMCP 2.0 Implementation Guide for MCP Gateway Server

A practical guide to using FastMCP 2.0 features for building an MCP gateway that proxies to downstream servers with per-agent access control.

## Core FastMCP 2.0 Features for Gateway Pattern

### 1. FastMCP.as_proxy() - Automatic Gateway Creation

The `as_proxy()` class method creates a proxy server that automatically connects to multiple downstream MCP servers, discovers their tools, and exposes them through a unified interface.

**Key capabilities:**
- Accepts MCPConfig dictionary or single MCPClient
- Automatically spawns stdio processes (uvx, npx, python)
- Establishes HTTP/SSE connections to remote servers
- Discovers and aggregates tools from all downstream servers
- Prefixes tool names with server identifier to avoid conflicts
- Routes tool calls to appropriate downstream server based on prefix

**Basic usage:**

```python
from fastmcp import FastMCP

config = {
    "mcpServers": {
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": "ghp_xxxxx"}
        },
        "filesystem": {
            "command": "uvx",
            "args": ["mcp-server-filesystem", "/workspace"]
        },
        "weather": {
            "url": "https://weather-api.example.com/mcp"
        }
    }
}

gateway = FastMCP.as_proxy(config, name="MCP Gateway Gateway")
```

**Configuration options:**
- `config`: MCPConfig dict or MCPClient instance
- `name`: Server name exposed to upstream clients
- `instructions`: Optional system instructions for the gateway
- `prefixes`: Optional custom prefixes instead of server names

### 2. MCPConfig Format - Defining Downstream Servers

FastMCP 2.0 natively supports the standard MCPConfig format used by Claude Desktop and other MCP clients.

**Structure:**

```python
{
    "mcpServers": {
        "<server_identifier>": {
            # For stdio transport (local processes)
            "command": "npx" | "uvx" | "python" | "node",
            "args": ["list", "of", "arguments"],
            "env": {
                "ENV_VAR": "value"
            },
            
            # OR for HTTP transport (remote servers)
            "url": "https://remote-server.com/mcp",
            "headers": {
                "Authorization": "Bearer token"
            }
        }
    }
}
```

**Stdio transport examples:**

```python
# npx-based server
"brave-search": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-brave-search"],
    "env": {
        "BRAVE_API_KEY": "BSA_xxxxx"
    }
}

# uvx-based server
"fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
}

# Direct Python execution
"context7": {
    "command": "python",
    "args": ["-m", "context7_mcp.server"],
    "env": {
        "CONTEXT7_API_KEY": "ctx7_xxxxx"
    }
}
```

**HTTP transport example:**

```python
"remote-analytics": {
    "url": "https://analytics.company.com/mcp",
    "headers": {
        "Authorization": "Bearer company_token_here",
        "X-Client-ID": "gateway-v1"
    }
}
```

### 3. Dynamic Configuration Loading

FastMCP 2.0 can load configurations dynamically from JSON files or environment variables, enabling users to manage their downstream servers without code changes.

**From JSON file:**

```python
import json
from pathlib import Path

def load_gateway_config(config_path: str) -> dict:
    """Load MCPConfig from JSON file"""
    with open(config_path, 'r') as f:
        return json.load(f)

config = load_gateway_config("~/.config/mcp-gateway/servers.json")
gateway = FastMCP.as_proxy(config, name="Dynamic Gateway")
```

**Example config file (`servers.json`):**

```json
{
    "mcpServers": {
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {
                "GITHUB_TOKEN": "${GITHUB_TOKEN}"
            }
        },
        "playwright": {
            "command": "uvx",
            "args": ["mcp-server-playwright"]
        }
    }
}
```

### 4. Middleware System - Per-Agent Access Control

FastMCP 2.0's middleware system works across all transports (stdio, HTTP, SSE) and provides hooks for intercepting MCP operations.

**Core middleware features:**
- `on_call_tool`: Intercept tool call requests
- `on_list_tools`: Filter available tools
- `on_list_resources`: Filter resources
- `MiddlewareContext`: Access to session_id, method, message, and server context
- State management: Persist data across requests via `set_state()`/`get_state()`

**Base middleware structure:**

```python
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import Tool

class AgentAccessMiddleware(Middleware):
    """
    Middleware to enforce per-agent access rules for servers and tools
    """
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Intercept tool calls and enforce access rules"""
        # Implementation details below
        pass
    
    async def on_list_tools(self, context: MiddlewareContext, call_next):
        """Filter tools list based on agent permissions"""
        # Implementation details below
        pass
```

### 5. Extracting Agent Identity from Tool Calls

Agents calling the gateway should provide an `agent_id` parameter with their tool calls. FastMCP middleware can extract this from the tool arguments.

**Implementation:**

```python
async def on_call_tool(self, context: MiddlewareContext, call_next):
    """Extract agent_id from tool arguments"""
    
    # Get the tool call message
    tool_call = context.message
    tool_name = tool_call.name  # e.g., "github_create_issue"
    arguments = tool_call.arguments or {}
    
    # Extract agent_id from arguments
    agent_id = arguments.get("agent_id")
    
    if not agent_id:
        # Fallback to session_id or default agent
        agent_id = context.session_id or "default_agent"
    
    # Remove agent_id from arguments before forwarding
    # to downstream server (they don't need to know about it)
    clean_arguments = {k: v for k, v in arguments.items() 
                      if k != "agent_id"}
    
    # Store agent_id in context for other middleware/tools
    context.set_state("current_agent", agent_id)
    
    # Proceed with cleaned arguments
    return await call_next(context)
```

**Agent tool call format:**

```python
# When agent calls a tool, it includes agent_id
{
    "method": "tools/call",
    "params": {
        "name": "github_create_issue",
        "arguments": {
            "agent_id": "frontend_agent",  # <-- Agent identification
            "repository": "myorg/myrepo",
            "title": "Bug report",
            "body": "Description..."
        }
    }
}
```

### 6. Access Rules Configuration

Define which agents can access which servers and tools through a configuration structure.

**Rules format:**

```python
access_rules = {
    "main_orchestrator": {
        "servers": [],  # No direct server access
        "tools": ["list_servers", "get_server_tools"]  # Only discovery tools
    },
    "researcher_agent": {
        "servers": ["brave-search", "fetch", "context7"],
        "tools": "*"  # All tools from allowed servers
    },
    "frontend_agent": {
        "servers": ["context7", "playwright"],
        "tools": {
            "context7": "*",  # All tools from context7
            "playwright": [  # Limited tools from playwright
                "playwright_navigate",
                "playwright_screenshot",
                "playwright_click"
            ]
        }
    },
    "backend_agent": {
        "servers": ["github", "database"],
        "tools": "*"
    }
}
```

**Loading from JSON file:**

```json
{
    "access_rules": {
        "researcher_agent": {
            "servers": ["brave-search", "fetch"],
            "tools": "*"
        },
        "frontend_agent": {
            "servers": ["playwright"],
            "tools": {
                "playwright": ["playwright_navigate", "playwright_screenshot"]
            }
        }
    }
}
```

### 7. Complete Middleware Implementation

Full implementation of access control middleware with both server-level and tool-level filtering.

```python
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from mcp.types import Tool

class AgentAccessControl(Middleware):
    """
    Enforces per-agent access rules for downstream servers and tools
    """
    
    def __init__(self, access_rules: dict):
        """
        Args:
            access_rules: Dict mapping agent names to their allowed servers/tools
        """
        self.access_rules = access_rules
    
    def _get_server_from_tool(self, tool_name: str) -> str:
        """Extract server prefix from prefixed tool name"""
        # Tool format: "servername_toolname"
        parts = tool_name.split("_", 1)
        return parts[0] if len(parts) > 1 else ""
    
    def _is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Check if agent has permission to call this tool"""
        
        # Get agent rules or deny by default
        agent_rules = self.access_rules.get(agent_id)
        if not agent_rules:
            return False
        
        # Extract server from prefixed tool name
        server = self._get_server_from_tool(tool_name)
        
        # Check if agent has access to this server
        allowed_servers = agent_rules.get("servers", [])
        if server not in allowed_servers:
            return False
        
        # Check tool-level permissions
        tools_config = agent_rules.get("tools")
        
        # If tools is "*", allow all tools from allowed servers
        if tools_config == "*":
            return True
        
        # If tools is a dict, check server-specific tool rules
        if isinstance(tools_config, dict):
            server_tools = tools_config.get(server, [])
            
            # If server has "*", allow all its tools
            if server_tools == "*":
                return True
            
            # Check if specific tool is in allowed list
            # Remove server prefix for comparison
            tool_base_name = tool_name.replace(f"{server}_", "", 1)
            return tool_base_name in server_tools
        
        return False
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Enforce access rules on tool calls"""
        
        tool_call = context.message
        arguments = tool_call.arguments or {}
        
        # Extract agent identity
        agent_id = arguments.get("agent_id") or context.session_id
        
        if not agent_id:
            raise ToolError("No agent identity provided")
        
        # Check if tool is allowed for this agent
        if not self._is_tool_allowed(agent_id, tool_call.name):
            raise ToolError(
                f"Agent '{agent_id}' is not authorized to call tool "
                f"'{tool_call.name}'"
            )
        
        # Store agent name in context state
        context.set_state("current_agent", agent_id)
        
        # Remove agent_id from arguments before forwarding
        clean_arguments = {k: v for k, v in arguments.items() 
                          if k != "agent_id"}
        
        # Update message with cleaned arguments
        tool_call.arguments = clean_arguments
        
        # Allow the request to proceed
        return await call_next(context)
    
    async def on_list_tools(self, context: MiddlewareContext, call_next):
        """Filter tools list based on agent permissions"""
        
        # Get the full list of tools from downstream servers
        response = await call_next(context)
        
        # Extract agent identity from stored state or session
        agent_id = context.get_state("current_agent") or context.session_id
        
        if not agent_id or agent_id not in self.access_rules:
            # Return empty list for unknown agents
            return []
        
        # Filter tools based on agent permissions
        filtered_tools = [
            tool for tool in response.tools
            if self._is_tool_allowed(agent_id, tool.name)
        ]
        
        # Return filtered response
        response.tools = filtered_tools
        return response
```

### 8. Adding Custom Discovery Tools

Add `list_servers` and `get_server_tools` as native tools on the gateway itself, not proxied from downstream servers.

```python
from fastmcp import FastMCP, Context
from mcp.types import Tool

@gateway.tool
async def list_servers(agent_id: Optional[str] = None, ctx: Context) -> list[dict]:
    """
    List all MCP servers available to the calling agent

    Args:
        agent_id: Identifier of the agent making the request (optional, uses fallback chain)

    Returns:
        List of server information dicts
    """
    # Get agent's access rules
    access_rules = ctx.get_state("access_rules") or {}
    agent_rules = access_rules.get(agent_id, {})
    allowed_servers = agent_rules.get("servers", [])
    
    # Get full server config
    mcp_config = ctx.get_state("mcp_config") or {}
    all_servers = mcp_config.get("mcpServers", {})
    
    # Return info for allowed servers only
    server_list = []
    for server_name in allowed_servers:
        if server_name in all_servers:
            server_config = all_servers[server_name]
            server_list.append({
                "name": server_name,
                "transport": "stdio" if "command" in server_config else "http",
                "description": server_config.get("description", "")
            })
    
    return server_list


@gateway.tool
async def get_server_tools(
    server_name: str,
    agent_id: Optional[str] = None,
    ctx: Context
) -> list[dict]:
    """
    Get all tools available from a specific server for the calling agent
    
    Args:
        server_name: Name of the downstream MCP server
        agent_id: Identifier of the agent making the request
    
    Returns:
        List of tool information dicts
    """
    # Verify agent has access to this server
    access_rules = ctx.get_state("access_rules") or {}
    agent_rules = access_rules.get(agent_id, {})
    allowed_servers = agent_rules.get("servers", [])
    
    if server_name not in allowed_servers:
        return []
    
    # Get all tools from the gateway
    all_tools = await ctx.list_tools()
    
    # Filter to tools from requested server
    server_tools = [
        {
            "name": tool.name.replace(f"{server_name}_", "", 1),
            "description": tool.description or "",
            "input_schema": tool.inputSchema
        }
        for tool in all_tools
        if tool.name.startswith(f"{server_name}_")
    ]
    
    # Apply tool-level filtering based on agent rules
    tools_config = agent_rules.get("tools")
    
    if tools_config == "*":
        return server_tools
    
    if isinstance(tools_config, dict):
        allowed_tool_names = tools_config.get(server_name, [])
        
        if allowed_tool_names == "*":
            return server_tools
        
        # Filter to allowed tools only
        return [
            tool for tool in server_tools
            if tool["name"] in allowed_tool_names
        ]
    
    return []
```

### 9. State Management for Configuration

Store configurations in gateway context so middleware and tools can access them.

```python
from fastmcp import FastMCP

# Load configurations
mcp_config = load_gateway_config("servers.json")
access_rules = load_access_rules("access_rules.json")

# Create gateway with proxy
gateway = FastMCP.as_proxy(mcp_config, name="MCP Gateway Gateway")

# Store configs in gateway context for middleware/tools to access
gateway.set_state("mcp_config", mcp_config)
gateway.set_state("access_rules", access_rules)

# Add middleware
gateway.add_middleware(AgentAccessControl(access_rules))

# Add custom tools (list_servers and get_server_tools from above)
# ... (decorator-based tools defined earlier)

# Run the gateway
gateway.run(transport="http", port=8000)
```

### 10. ProxyClient for Advanced Scenarios

For more granular control over downstream connections, use `ProxyClient` directly instead of `as_proxy()`.

**Use cases:**
- Custom connection lifecycle management
- Session-specific downstream connections
- Advanced routing logic
- Error handling and retries

**Basic usage:**

```python
from fastmcp.client import ProxyClient

# Create client for specific downstream server
github_client = ProxyClient(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_TOKEN": "ghp_xxxxx"}
)

# Or for HTTP server
weather_client = ProxyClient(
    url="https://weather-api.example.com/mcp"
)

# Connect and use
async with github_client:
    tools = await github_client.list_tools()
    result = await github_client.call_tool(
        "create_issue",
        {"repo": "myorg/myrepo", "title": "Bug"}
    )
```

**When to use ProxyClient:**
- Implementing custom routing logic beyond simple prefixing
- Need to manage connections with specific lifecycle requirements
- Building a multi-tenant gateway with per-user server instances
- Advanced error handling or connection pooling

### 11. Complete Gateway Setup Example

Putting it all together:

```python
from fastmcp import FastMCP, Context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
import json
from pathlib import Path

# Load configurations
def load_config(path: str) -> dict:
    with open(Path(path).expanduser(), 'r') as f:
        return json.load(f)

mcp_config = load_config("~/.config/mcp-gateway/servers.json")
access_rules = load_config("~/.config/mcp-gateway/access_rules.json")

# Create gateway with automatic proxying
gateway = FastMCP.as_proxy(
    mcp_config,
    name="MCP Gateway Gateway",
    instructions="Central gateway for managing access to downstream MCP servers"
)

# Store configs in gateway state
gateway.set_state("mcp_config", mcp_config)
gateway.set_state("access_rules", access_rules)

# Add access control middleware
gateway.add_middleware(AgentAccessControl(access_rules))

# Add discovery tools
@gateway.tool
async def list_servers(agent_id: str, ctx: Context) -> list[dict]:
    """List servers available to agent"""
    # Implementation from section 8
    pass

@gateway.tool
async def get_server_tools(
    server_name: str,
    agent_id: str,
    ctx: Context
) -> list[dict]:
    """Get tools from specific server"""
    # Implementation from section 8
    pass

# Run gateway on HTTP
if __name__ == "__main__":
    gateway.run(transport="http", port=8000)
```

### 12. Alternative: mount() for Manual Composition

If you need more control than `as_proxy()` provides, use `mount()` to manually compose multiple FastMCP servers.

```python
from fastmcp import FastMCP

# Create individual proxy servers
github = FastMCP.as_proxy({
    "mcpServers": {
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"]
        }
    }
})

filesystem = FastMCP.as_proxy({
    "mcpServers": {
        "fs": {
            "command": "uvx",
            "args": ["mcp-server-filesystem", "/workspace"]
        }
    }
})

# Create main gateway and mount sub-servers
gateway = FastMCP(name="Main Gateway")
gateway.mount("/github", github)
gateway.mount("/filesystem", filesystem)

# Add middleware and custom tools to main gateway
gateway.add_middleware(AgentAccessControl(access_rules))

# Run
gateway.run(transport="http", port=8000)
```

**Note:** `as_proxy()` is simpler and recommended for most gateway use cases.

## Summary: Key FastMCP 2.0 Features for Gateway

1. **FastMCP.as_proxy()**: One-line gateway creation from MCPConfig
2. **MCPConfig format**: Standard configuration for stdio and HTTP servers
3. **Automatic tool discovery**: Finds and prefixes tools from all downstream servers
4. **Middleware system**: Cross-transport hooks for access control
5. **MiddlewareContext**: Access to session_id, method, message, and state
6. **State management**: Store configs and agent data with `set_state()`/`get_state()`
7. **Custom tools**: Add gateway-specific tools like `list_servers` via decorators
8. **ProxyClient**: Fine-grained control for advanced routing scenarios
9. **Dynamic configuration**: Load server and access rules from JSON files
10. **Tool filtering**: Per-agent tool list filtering via `on_list_tools` middleware

## Implementation Checklist

- [ ] Define MCPConfig JSON with all downstream servers
- [ ] Define access_rules JSON with per-agent server/tool permissions
- [ ] Create gateway with `FastMCP.as_proxy(mcp_config)`
- [ ] Store configs in gateway state for middleware/tools to access
- [ ] Implement `AgentAccessControl` middleware
- [ ] Add `list_servers` and `get_server_tools` custom tools
- [ ] Register middleware with `gateway.add_middleware()`
- [ ] Test with different agent identities
- [ ] Run gateway with `gateway.run(transport="http", port=8000)`
- [ ] Configure Claude Code to use gateway as MCP server

## Next Steps

1. Start with a minimal config of 2-3 downstream servers
2. Implement basic middleware without tool-level filtering
3. Test agent access control with sample agents
4. Add tool-level filtering once server-level filtering works
5. Implement the discovery tools (list_servers, get_server_tools)
6. Build configuration management UI (future enhancement)
