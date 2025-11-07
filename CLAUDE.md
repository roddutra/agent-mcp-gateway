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

```bash
# Install dependencies
uv sync

# Run gateway
uv run python main.py

# Add dependency
uv add <package-name>

# Add dev dependency
uv add --dev <package-name>

# Update dependencies
uv lock --upgrade
```

See README.md for production MCP client configuration.

## Release Management

**CRITICAL:** NEVER bump version in `pyproject.toml` without explicit user approval.

**When version is updated:**
- Update BOTH `pyproject.toml` and `CHANGELOG.md` together
- Run `uv lock` to sync lockfile
- DO NOT release without user approval

**To release:** See `docs/release-process.md` for complete workflow. Key: pushing the git tag (not just commits) triggers automated PyPI publishing via GitHub Actions.

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

1. **Gateway Server** - FastMCP-based, exposes 3 gateway tools + 1 debug tool, uses `FastMCP.as_proxy()` for downstream proxying
2. **Policy Engine** - Stateless evaluation with deny-before-allow precedence, wildcard support
3. **Proxy Layer** - Transparent forwarding, stdio/HTTP transports, OAuth auto-detection
4. **Session Manager** - Per-agent isolation via FastMCP context

### Gateway Tools (Exposed to Agents)

```python
list_servers(agent_id: Optional[str], include_metadata: bool) -> List[Server]
get_server_tools(agent_id: Optional[str], server: str, names: Optional[List[str]],
                 pattern: Optional[str], max_schema_tokens: Optional[int]) -> List[Tool]
execute_tool(agent_id: Optional[str], server: str, tool: str,
             args: dict, timeout_ms: Optional[int]) -> Any
```

All tools accept optional `agent_id` (uses fallback chain if not provided). See README.md for detailed parameter descriptions.

### Configuration Structure

**MCP Servers Config** (`.mcp.json`):
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-name"],
      "env": {"API_KEY": "${API_KEY}"}
    }
  }
}
```

**Gateway Rules Config** (`.mcp-gateway-rules.json`):
```json
{
  "agents": {
    "agent-name": {
      "allow": {"servers": ["server-name"], "tools": {"server-name": ["*"]}},
      "deny": {"tools": {"server-name": ["dangerous_*"]}}
    }
  },
  "defaults": {"deny_on_missing_agent": false}
}
```

See `config/*.example` files for complete examples and README.md for detailed configuration guide.

### Policy Evaluation Rules (CRITICAL - DO NOT CHANGE)

**Exact precedence order with short-circuit evaluation:**
1. Explicit deny rules → if match, DENY and STOP
2. Wildcard deny rules → if match, DENY and STOP
3. Explicit allow rules → if match, ALLOW and STOP
4. Wildcard allow rules → if match, ALLOW and STOP
5. Implicit grant - if server allowed but no tool rules specified for that server → ALLOW and STOP
6. Default policy → DENY

**Critical principle:** All deny rules (explicit + wildcard) checked before any allow rules.

**Implicit Grant Behavior:**
- If agent has server access AND no `allow.tools.{server}` entry → all tools from that server implicitly granted
- `allow.tools.{server}` entries are server-specific and narrow access for that server only
- `deny.tools.{server}` entries are server-specific and filter tools for that server only (evaluated in steps 1-2)

### Agent Identity

All gateway tools accept optional `agent_id` parameter. When not provided, uses fallback chain:

1. Explicit `agent_id` in tool call (highest priority)
2. `GATEWAY_DEFAULT_AGENT` env var
3. Agent named "default" in rules (if `deny_on_missing_agent` is false)
4. Error if none configured

See `docs/claude-code-subagent-mcp-limitations.md` for single-agent vs multi-agent configuration details.

### OAuth Support

Gateway auto-detects OAuth-protected downstream servers (Notion, GitHub, etc.) via 401 responses. Zero configuration needed - just add server URL to `.mcp.json`. Browser auth happens once, then tokens are cached.

See `docs/oauth-user-guide.md` for setup and troubleshooting.

## Tool Description Standards

Gateway tools must be **self-documenting** - agents in Claude Desktop and similar MCP clients have no custom prompts, only tool descriptions.

**Concise is key:** Default assumption is Claude is already smart. Only add context Claude doesn't have.

**Tool descriptions:**
- Single sentence, include workflow if relevant
- No Args/Returns sections (use `Annotated[Type, "description"]` and Pydantic output models instead)

**Parameter descriptions:** 4-7 words, actionable (e.g., "leave empty if not provided to you", "Server name from list_servers")

**Output field descriptions:** 3-6 words, clarify ambiguities (e.g., "less than total_available is normal due to filtering")

## FastMCP 2.0 Implementation Patterns

Key patterns used in this project:
- **Gateway creation:** `FastMCP.as_proxy(mcp_config)` for automatic downstream proxying
- **Middleware:** `AgentAccessControl(Middleware)` with `on_call_tool` hook for policy enforcement
- **Custom tools:** `@gateway.tool` decorator with `Context` for state access
- **State management:** `gateway.set_state()` and `ctx.get_state()` for config sharing

See `docs/fastmcp-implementation-guide.md` for complete code examples and detailed patterns.

## Implementation Milestones

- **M0: Foundation** - Gateway with stdio, config loading, list_servers, audit logging
- **M1: Core** - get_server_tools, execute_tool, session isolation, metrics
- **M2: Production** - HTTP transport, health checks, error handling
- **M3: DX** - Single-agent mode, config validation CLI, Docker container

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GATEWAY_MCP_CONFIG` | `.mcp.json` | MCP server definitions path |
| `GATEWAY_RULES` | `.mcp-gateway-rules.json` | Agent policies path |
| `GATEWAY_DEFAULT_AGENT` | None | Default agent when agent_id not provided |
| `GATEWAY_DEBUG` | `false` | Enable debug mode + get_gateway_status tool |
| `GATEWAY_AUDIT_LOG` | `~/.cache/agent-mcp-gateway/logs/audit.jsonl` | Audit log path |
| `GATEWAY_TRANSPORT` | `stdio` | Transport type (stdio or http) |
| `GATEWAY_INIT_STRATEGY` | `eager` | Initialization strategy (eager or lazy) |

**Note:** `GATEWAY_DEBUG=true` enables `get_gateway_status` diagnostic tool. For security considerations and detailed env var descriptions, see README.md Environment Variables Reference.

## Error Codes

- `DENIED_BY_POLICY` - Agent lacks permission for requested operation
- `SERVER_UNAVAILABLE` - Downstream MCP server unreachable
- `TOOL_NOT_FOUND` - Requested tool doesn't exist
- `INVALID_AGENT_ID` - Missing or unknown agent identifier
- `FALLBACK_AGENT_NOT_IN_RULES` - Configured fallback agent not found in gateway rules
- `NO_FALLBACK_CONFIGURED` - No agent_id provided and no fallback agent configured
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
- `/docs/pypi-readme-transformation.md` - Build-time README transformation for PyPI compatibility
- `/docs/release-process.md` - Version bumping, building, and publishing workflow for PyPI releases

## Design Philosophy

- **Zero modifications to downstream MCP servers** - Full compatibility with existing servers
- **Context preservation** - 90%+ reduction in upfront token usage
- **Deny-before-allow security** - Safe by default
- **Principle of least privilege** - No implicit "allow all" access, even with fallbacks
- **Transparent proxying** - Downstream servers unaware of gateway
- **Audit everything** - Complete operation logging
- **Configuration-driven** - No code changes for permission updates
- **Flexible agent identity** - Optional agent_id with secure fallback chain

## Documentation Guidelines

### Writing Principles

When writing documentation for this project, apply the **"Concise is key" principle**:

**Context window is a public good.** Default assumption: **Claude is already very smart**

Challenge each piece of information:
- "Does Claude really need this explanation?"
- "Can I assume Claude knows this?"
- "Does this paragraph justify its token cost?"

**Know Your Audience:**

Documentation has two types of consumers:
- **Human end-users** - Need sufficient context, practical examples, and clear explanations
- **AI coding agents (like Claude Code)** - Already possess broad knowledge; need only project-specific, essential context

**Balance Requirements:**
- Not too verbose (exhausting for humans to read)
- Not too shallow (missing key information)
- Not too token-heavy (LLMs understand general concepts; focus on what's unique to this project)

**Reference, Don't Repeat:** Information well-documented elsewhere should be referenced, not duplicated.

### Permanent Documentation (committed to git)

Store in appropriate `docs/` subdirectories based on content type:

**docs/milestones/**
- Milestone completion reports (m0-success-report.md, m1-success-report.md, etc.)
- Success criteria validation
- Performance metrics and test results
- Historical records of milestone achievements

**docs/specs/**
- Product requirements (PRD.md)
- Milestone specifications (m0-foundation.md, m1-core.md, m2-production.md, m3-dx.md)
- Technical specifications
- Architecture decision records

**docs/** (root)
- Quick start guides (quickstart-config.md)
- Framework summaries (validation-framework-summary.md)
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

1. **No documentation in project root** - All docs must be in `docs/` or its subdirectories
2. **Use relative paths** - Never use absolute paths like `/Users/username/...` in documentation
3. **Choose permanent vs temporary carefully** - If it's valuable for future reference, it's permanent
4. **Temporary docs are truly temporary** - Move to permanent location or delete when work is done
5. **Update existing docs** - Don't create duplicates; update existing documentation when appropriate
6. **Keep docs concise** - Reference other docs instead of duplicating content; only include information that is necessary, valuable, or unique
7. **No comments in JSON files** - JSON doesn't support comments; users should be able to copy example files without cleaning content
8. **Reference, don't duplicate** - If information is well-documented elsewhere, link to it rather than repeating it

### Documentation Content Guidelines

**What to include in each file type:**

**CLAUDE.md (this file):**
- High-level overviews with links to detailed docs
- Critical implementation patterns specific to this project
- Information Claude needs for immediate context
- References to detailed documentation for deep dives

**README.md:**
- User-facing quick start and usage instructions
- Essential configuration examples
- Links to detailed guides for advanced topics

**Configuration Examples (config/*.example):**
- Valid, copy-paste ready configurations only
- No comments or explanations (especially not in JSON files)
- Examples should be self-explanatory through naming
- Documentation belongs in README.md or dedicated guides

**Detailed Guides (docs/*.md):**
- Comprehensive explanations and tutorials
- Troubleshooting procedures
- Architecture deep dives
- Reference material for specific features

### Documentation Naming Convention

Use kebab-case for all documentation files unless the user specifies otherwise or the file already has a well-established casing convention (e.g., README.md, CLAUDE.md, PRD.md).
