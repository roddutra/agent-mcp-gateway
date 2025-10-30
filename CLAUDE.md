# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent MCP Gateway is an MCP server that acts as a proxy/gateway to multiple downstream MCP servers. It enables per-agent/subagent access control, solving Claude Code's context window waste where all MCP tool definitions load upfront instead of being discovered on-demand.

**Core Problem:** When multiple MCP servers are configured, all tools from all servers (5,000-50,000+ tokens) load into every agent's context at startup. This wastes 80-95% of context on unused tools.

**Solution:** Gateway exposes only 3 minimal tools (~400 tokens) that allow agents to discover and request specific tools on-demand based on configurable access rules.

## Tech Stack

- **Python 3.12+** (required)
- **FastMCP 2.0** (version 2.13.0.1+) - MCP server framework
- **uv** - Package and project manager

## Development Commands

### Environment Setup
```bash
# Install dependencies
uv sync

# Run the gateway
uv run python main.py
```

### Package Management
```bash
# Add a new dependency
uv add <package-name>

# Add a dev dependency
uv add --dev <package-name>

# Update dependencies
uv lock --upgrade
```

## Architecture

### Gateway Model

```
Agent → Gateway (3 tools, ~400 tokens) → Policy Engine → Downstream MCP Servers (100s of tools)
         ↓
      Audit Log
```

**Traditional MCP:** All tools loaded upfront → Agent discovers what's available
**Gateway MCP:** Minimal interface loaded → Agent requests what it needs → Gateway provides filtered access

### Core Components

1. **Gateway Server** (FastMCP-based)
   - Exposes 3 gateway tools: `list_servers`, `get_server_tools`, `execute_tool`
   - All tools require `agent_id` parameter
   - Built using `FastMCP.as_proxy()` for automatic downstream server proxying

2. **Policy Engine** (Stateless)
   - Evaluates agent permissions against configured rules
   - Deny-before-allow precedence
   - Supports wildcards and hierarchical agents

3. **Proxy Layer** (Transparent)
   - Forwards tool executions to downstream servers
   - Handles stdio (npx/uvx) and HTTP transports
   - Automatic tool prefixing to avoid naming conflicts

4. **Session Manager**
   - Per-agent session isolation
   - State management via FastMCP context

### Gateway Tools (Exposed to Agents)

```python
list_servers(agent_id: str, include_metadata: bool = False) -> List[Server]
# Returns MCP servers this agent can access based on policy rules

get_server_tools(
    agent_id: str,
    server: str,
    names: Optional[List[str]] = None,
    pattern: Optional[str] = None,
    max_schema_tokens: Optional[int] = None
) -> List[Tool]
# Returns tool definitions from a server, filtered by agent permissions

execute_tool(
    agent_id: str,
    server: str,
    tool: str,
    args: dict,
    timeout_ms: Optional[int] = None
) -> Any
# Proxies tool execution to downstream server
```

### Configuration Structure

**MCP Servers Config** (`.mcp.json`):
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
    },
    "postgres": {
      "command": "uvx",
      "args": ["mcp-server-postgres"]
    }
  }
}
```

**Note:** `.mcp.json` is the standard MCP configuration file format used by Claude Code and other coding agents.

**Gateway Rules Config** (`.mcp-gateway-rules.json`):
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
    }
  },
  "defaults": {
    "deny_on_missing_agent": true
  }
}
```

### Policy Evaluation Rules (CRITICAL - DO NOT CHANGE)

**Exact precedence order:**
1. Explicit deny rules
2. Explicit allow rules
3. Wildcard deny rules
4. Wildcard allow rules
5. Default policy

### Agent Identity Workaround

**Important:** Claude Code does not natively pass subagent identity to MCP servers. This gateway requires agents to explicitly include `agent_id` parameter in all tool calls.

Each agent/subagent configuration must include instructions to always pass their identity:
```markdown
**CRITICAL**: When calling ANY gateway tool, you MUST include an "agent_id" parameter set to "your-agent-name".
```

See `docs/claude-code-subagent-mcp-limitations.md` for full details on this limitation and implementation.

## FastMCP 2.0 Implementation Patterns

### Creating the Gateway

```python
from fastmcp import FastMCP

# Load downstream server config
mcp_config = load_config(".mcp.json")

# Create gateway with automatic proxying
gateway = FastMCP.as_proxy(mcp_config, name="Agent MCP Gateway")

# Store configs in gateway state for middleware access
gateway.set_state("mcp_config", mcp_config)
gateway.set_state("access_rules", access_rules)
```

### Middleware for Access Control

```python
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError

class AgentAccessControl(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        # Extract agent_id from arguments
        agent_id = context.message.arguments.get("agent_id")

        # Validate access permissions
        if not self._is_tool_allowed(agent_id, context.message.name):
            raise ToolError(f"Agent '{agent_id}' denied access")

        # Remove agent_id before forwarding to downstream
        clean_args = {k: v for k, v in context.message.arguments.items()
                      if k != "agent_id"}
        context.message.arguments = clean_args

        return await call_next(context)
```

### Custom Tools

```python
@gateway.tool
async def list_servers(agent_id: str, ctx: Context) -> list[dict]:
    """List servers available to the calling agent"""
    access_rules = ctx.get_state("access_rules")
    # Filter servers based on agent permissions
    # Return filtered list
```

## Implementation Milestones

- **M0: Foundation** - Gateway with stdio, config loading, list_servers, audit logging
- **M1: Core** - get_server_tools, execute_tool, session isolation, metrics
- **M2: Production** - HTTP transport, health checks, error handling
- **M3: DX** - Single-agent mode, config validation CLI, Docker container

## Environment Variables

```bash
GATEWAY_MCP_CONFIG=.mcp.json               # MCP server definitions (default: .mcp.json, fallback: ./config/.mcp.json)
GATEWAY_RULES=.mcp-gateway-rules.json      # Agent policies (default: .mcp-gateway-rules.json, fallback: ./config/.mcp-gateway-rules.json)
GATEWAY_DEFAULT_AGENT=developer            # Single-agent mode fallback
GATEWAY_TRANSPORT=stdio                    # stdio|http
GATEWAY_INIT_STRATEGY=eager                # eager|lazy
```

## Error Codes

- `DENIED_BY_POLICY` - Agent lacks permission for requested operation
- `SERVER_UNAVAILABLE` - Downstream MCP server unreachable
- `TOOL_NOT_FOUND` - Requested tool doesn't exist
- `INVALID_AGENT_ID` - Missing or unknown agent identifier
- `TIMEOUT` - Operation exceeded time limit

## Performance Targets

- `list_servers`: <50ms (P95)
- `get_server_tools`: <300ms (P95)
- `execute_tool` overhead: <30ms (P95)
- Overall added latency: <100ms (P95)

## Key Documentation

- `/docs/specs/PRD.md` - Complete product requirements and specifications
- `/docs/fastmcp-implementation-guide.md` - FastMCP 2.0 patterns and examples
- `/docs/claude-code-subagent-mcp-limitations.md` - Agent identity workaround details

## Design Philosophy

- **Zero modifications to downstream MCP servers** - Full compatibility with existing servers
- **Context preservation** - 90%+ reduction in upfront token usage
- **Deny-before-allow security** - Safe by default
- **Transparent proxying** - Downstream servers unaware of gateway
- **Audit everything** - Complete operation logging
- **Configuration-driven** - No code changes for permission updates

## Documentation Guidelines

### Permanent Documentation (committed to git)

Store in appropriate `docs/` subdirectories based on content type:

**docs/milestones/**
- Milestone completion reports (M0_SUCCESS_REPORT.md, M1_SUCCESS_REPORT.md, etc.)
- Success criteria validation
- Performance metrics and test results
- Historical records of milestone achievements

**docs/specs/**
- Product requirements (PRD.md)
- Milestone specifications (M0-Foundation.md, M1-Core.md, M2-Production.md, M3-DX.md)
- Technical specifications
- Architecture decision records

**docs/** (root)
- Quick start guides (QUICKSTART_CONFIG.md)
- Framework summaries (VALIDATION_FRAMEWORK_SUMMARY.md)
- Implementation guides (fastmcp-implementation-guide.md)
- General documentation that doesn't fit other categories

### Temporary Documentation (NOT committed to git)

Store in `docs/temp/` (gitignored) for work-in-progress content:

**docs/temp/**
- Work-in-progress feature documentation
- Troubleshooting notes for open bugs
- Investigation findings (not yet resolved)
- Draft documentation being reviewed
- Session handoff notes (use /session-doc slash command)
- Temporary reference materials

**Examples:**
- `docs/temp/bug-hot-reload-investigation.md` - Active bug troubleshooting
- `docs/temp/feature-draft-http-transport.md` - Feature design in progress
- `docs/temp/session-2025-10-30.md` - Development session context

### Important Rules

1. **No documentation in project root** - All docs must be in `docs/` or subdirectories
2. **Use relative paths** - Never use absolute paths like `/Users/username/...` in documentation
   - ✓ Correct: `src/config.py`, `tests/test_config.py`
   - ✗ Incorrect: `/Users/roddutra/Developer/--personal/agent-mcp-gateway/src/config.py`
3. **Choose permanent vs temporary carefully** - If it's valuable for future reference, it's permanent
4. **Temporary docs are truly temporary** - Move to permanent location or delete when work is done
5. **Update existing docs** - Don't create duplicates; update existing documentation when appropriate
