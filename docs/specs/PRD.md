# Agent MCP Gateway PRD v1.1

Context Window-Preserving MCP Proxy with Dynamic Discovery of Servers and Tools Based on Agent-Specific Rules

---

## Problem Statement

### Current Challenges

When multiple MCP servers are configured in development environments (Claude Code, Cursor, VS Code), the system loads all tool definitions from all servers into every agent's context window at startup:

1. **Context Window Exhaustion**
   - All tools from all servers loaded upfront (5,000-50,000+ tokens)
   - 80-95% of loaded tools never used by individual agents
   - Context needed for actual work gets consumed by unused tool definitions

2. **No Granular Control**
   - All-or-nothing access per MCP server
   - Cannot restrict specific tools within a server
   - Cannot assign different tool sets to different agent roles

3. **Resource Impact**
   - 2-5x higher API costs from inflated context
   - Slower processing with unnecessary definitions
   - Adding new MCP servers becomes prohibitively expensive

---

## Solution Overview

### Core Concept

The Agent MCP Gateway acts as a single MCP server that proxies to multiple downstream MCP servers based on configurable per-agent rules. Instead of loading thousands of tool definitions upfront, agents load only ~400 tokens of gateway tools and request specific tools on-demand.

**Key Innovation:** Invert the traditional MCP loading model:
- **Traditional:** Load all tools upfront → Agent discovers what's available
- **Gateway Model:** Load minimal interface → Agent requests what it needs → Gateway provides filtered access

### Gateway Tools (Exposed to Agents)

The gateway exposes only these tools to agents (total ~400 tokens vs 5,000-50,000+ for direct loading):

```python
# All tools accept optional agent_id parameter with configurable fallback

list_servers(agent_id: Optional[str] = None, include_metadata: bool = False) -> List[Server]
# Returns MCP servers this agent can access based on policy rules
# Enables discovery without loading all tool definitions
# agent_id is optional - uses fallback chain if not provided

get_server_tools(
    agent_id: Optional[str] = None,
    server: str,
    names: Optional[List[str]] = None,        # Specific tool names
    pattern: Optional[str] = None,             # Wildcards: "get_*"
    max_schema_tokens: Optional[int] = None   # Token budget limit
) -> List[Tool]
# Returns tool definitions from a server, filtered by agent permissions
# Loaded on-demand, not at startup
# agent_id is optional - uses fallback chain if not provided

execute_tool(
    agent_id: Optional[str] = None,
    server: str,
    tool: str,
    args: dict,
    timeout_ms: Optional[int] = None
) -> Any
# Proxies tool execution to downstream server
# Handles all protocol translation and response forwarding
# agent_id is optional - uses fallback chain if not provided
```

**Agent Identity Fallback Chain:**
When `agent_id` is not provided:
1. Use `GATEWAY_DEFAULT_AGENT` environment variable (highest priority)
2. Use agent named "default" in gateway rules (if `deny_on_missing_agent` is false)
3. Return error if neither configured

**Security:** Follows principle of least privilege - no implicit "allow all" access.

This minimal interface replaces loading all downstream tools upfront, allowing agents to:
1. Discover available servers (`list_servers`)
2. Load only needed tool definitions (`get_server_tools`)
3. Execute tools without bloating context (`execute_tool`)

### Example Impact

**Scenario:** 10 MCP servers with 50 tools each
- **Without Gateway:** Every agent loads 500 tool definitions (~25,000 tokens)
- **With Gateway:** Every agent loads 3 gateway tools (~400 tokens)
- **Savings:** 98% context reduction, tools loaded only when needed

---

## Success Metrics

| Metric | Target | Priority |
|--------|--------|----------|
| Context reduction | >90% | P0 |
| Added latency (p95) | <100ms | P0 |
| Policy compliance | 100% | P0 |
| Compatibility | Zero modifications to existing MCPs | P0 |

---

## Configuration

### MCP Servers (standard format)
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
    }
  }
}
```

### Gateway Rules
```json
{
  "agents": {
    "researcher": {
      "allow": {
        "servers": ["brave-search"],
        "tools": {"brave-search": ["*"]}
      }
    },
    "backend": {
      "allow": {
        "servers": ["postgres"],
        "tools": {"postgres": ["query", "list_*"]}
      },
      "deny": {
        "tools": {"postgres": ["drop_*"]}
      }
    },
    "default": {
      "deny": {
        "servers": ["*"]
      }
    }
  },
  "defaults": {
    "deny_on_missing_agent": false
  }
}
```

**Note:** The "default" agent provides secure fallback permissions when `agent_id` is not provided.

### Policy Rules
1. Explicit deny > allow
2. Wildcards supported (`get_*`)
3. Hierarchical agents (`team.role`)

---

## Architecture

```
Agent → Gateway (3 tools) → Policy Engine → MCP Servers (100s of tools)
         ↓
      Audit Log
```

**Components:**
- **Gateway Server:** FastMCP stdio/HTTP
- **Policy Engine:** Stateless evaluation
- **Proxy Layer:** Transparent forwarding
- **Session Manager:** Per-agent isolation

**Transports:** stdio (npx/uvx), HTTP (streaming)

---

## Requirements

### Core (P0)
- [x] Expose only gateway tools at startup
- [x] Accept optional `agent_id` with secure fallback chain
- [x] Apply deny-before-allow policies
- [x] Proxy transparently to downstream
- [x] Isolate sessions per agent
- [x] Support stdio transports (HTTP in M2)
- [x] Audit all operations
- [x] Hot reload configurations at runtime
- [x] Thread-safe policy operations

### Performance (P95)
- `list_servers`: <50ms
- `get_server_tools`: <300ms  
- `execute_tool` overhead: <30ms

### Errors
```json
{
  "error": {
    "code": "DENIED_BY_POLICY",
    "message": "Agent 'frontend' denied tool 'drop_table'",
    "rule": "agents.frontend.deny.tools.postgres[0]"
  }
}
```

Codes: `DENIED_BY_POLICY`, `SERVER_UNAVAILABLE`, `TOOL_NOT_FOUND`, `INVALID_AGENT_ID`, `FALLBACK_AGENT_NOT_IN_RULES`, `NO_FALLBACK_CONFIGURED`, `TIMEOUT`

---

## Implementation Milestones

### M0: Foundation
**📋 [View detailed tasks →](./m0-foundation.md)**

- Gateway with stdio
- Config loading
- `list_servers` with policies
- Audit logging

### M1: Core
**📋 [View detailed tasks →](./m1-core.md)**

- `get_server_tools` with filtering
- `execute_tool` with proxying
- Session isolation
- Metrics

### M2: Production
**📋 [View detailed tasks →](./m2-production.md)**

- HTTP transport
- Health checks
- Error handling

### M3: DX
**📋 [View detailed tasks →](./m3-dx.md)**

- Single-agent mode
- Config validation CLI
- Docker container  

---

## Use Cases

### Multi-Agent Team
```
Without Gateway: Each agent loads 10,000+ tokens
With Gateway: Each agent loads 400 tokens

Orchestrator → No tools
Researcher → Search tools only  
Frontend → Browser tools only
Backend → Database tools only
```

### Progressive Discovery
```python
# Agent workflow
servers = list_servers("researcher")
tools = get_server_tools("researcher", "brave-search")
result = execute_tool("researcher", "brave-search", "search", {"query": "..."})
```

---

## Environment Variables

```bash
GATEWAY_MCP_CONFIG=./.mcp.json                      # MCP server definitions (default: .mcp.json, fallback: ./config/.mcp.json)
GATEWAY_RULES=./.mcp-gateway-rules.json             # Gateway rules config (default: .mcp-gateway-rules.json, fallback: ./config/.mcp-gateway-rules.json)
GATEWAY_DEFAULT_AGENT=developer                     # Default agent when agent_id not provided (optional, IMPLEMENTED)
GATEWAY_TRANSPORT=stdio                             # stdio|http
GATEWAY_INIT_STRATEGY=eager                         # eager|lazy
```

**Agent Identity Behavior:**
- `GATEWAY_DEFAULT_AGENT` set: Uses specified agent when `agent_id` missing
- `deny_on_missing_agent: false` (Fallback Mode): Uses fallback chain (env var → "default" agent → error)
- `deny_on_missing_agent: true` (Strict Mode): Immediately rejects requests without `agent_id`, bypassing fallback chain entirely

The `deny_on_missing_agent` setting provides flexibility: use `false` in single-agent/development environments for convenience, or `true` in production multi-agent environments for strict access control.

---

## Definition of Done

- [x] Proxies to stdio MCPs (HTTP in M2)
- [x] Filters by agent policies
- [x] <100ms overhead (actually <30ms P95)
- [x] 100% audit coverage
- [x] Works with Claude Code/Cursor/VS Code
- [ ] Docker image available (M3)

---

## Appendix: Complete Examples

### Single Developer
```json
{
  "agents": {
    "developer": {"allow": {"servers": ["*"], "tools": {"*": ["*"]}}}
  },
  "defaults": {
    "deny_on_missing_agent": false
  }
}
```

**Usage:**
```bash
export GATEWAY_DEFAULT_AGENT=developer
uv run python main.py
```

### Team Setup
```json
{
  "agents": {
    "orchestrator": {
      "allow": {"servers": []}
    },
    "frontend": {
      "allow": {
        "servers": ["browser"],
        "tools": {"browser": ["navigate", "screenshot", "get_*"]}
      }
    },
    "backend": {
      "allow": {
        "servers": ["database"],
        "tools": {"database": ["query", "list_*"]}
      },
      "deny": {
        "tools": {"database": ["drop_*", "truncate_*"]}
      }
    }
  },
  "defaults": {"deny_on_missing_agent": true}
}
```

### Audit Log Entry
```json
{
  "timestamp": "2025-10-28T10:30:00Z",
  "agent_id": "researcher",
  "operation": "execute_tool",
  "server": "brave-search",
  "tool": "search",
  "decision": "ALLOW",
  "latency_ms": 145
}
```

---

## Implementation Notes

### High Freedom (Design Decisions)
- Session management strategy
- Caching approach
- Metric collection method
- Error retry logic

### Medium Freedom (Patterns)
```python
# Policy evaluation pattern
def evaluate_policy(agent_id, server, tool):
    # Check deny rules first
    # Then check allow rules
    # Apply wildcards
    # Return decision with rule
```

### Low Freedom (Critical Paths)
```python
# Exact policy precedence (DO NOT CHANGE)
1. Explicit deny rules
2. Explicit allow rules  
3. Wildcard deny rules
4. Wildcard allow rules
5. Default policy

# Agent ID extraction (MUST BE EXACT)
agent_id = params.get("agent_id")
if not agent_id:
    # Apply fallback chain
    agent_id = os.getenv("GATEWAY_DEFAULT_AGENT")
    if not agent_id:
        if config.deny_on_missing_agent:
            raise InvalidAgentError("agent_id required and no fallback configured")
        agent_id = "default"  # Use "default" agent from rules
```

---

## Key Documentation

- **FastMCP 2.0**
  - Proxy Servers (IMPORTANT): `https://gofastmcp.com/servers/proxy`
  - Middleware (IMPORTANT): `https://gofastmcp.com/servers/middleware`
  - Server: `https://gofastmcp.com/servers/server`
  - Tools: `https://gofastmcp.com/servers/tools`
  - Server Composition (importing & mounting servers): `https://gofastmcp.com/servers/composition`
  - MCP Client: `https://gofastmcp.com/clients/client`
  - Context7 MCP Library ID: `jlowin/fastmcp`
- **Model Context Protocol**
  - Lifecycle: `https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle`
  - Transports: `https://modelcontextprotocol.io/specification/2025-06-18/basic/transports`
  - Tools: `https://modelcontextprotocol.io/specification/2025-06-18/server/tools`