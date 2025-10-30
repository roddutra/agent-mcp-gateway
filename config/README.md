# Configuration Directory

This directory contains configuration files for the Agent MCP Gateway.

## Configuration Files

### `.mcp.json`
Standard MCP server configuration defining downstream MCP servers. This file follows the Claude Code MCP configuration format.

**Structure:**
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx|uvx|node|python",
      "args": ["..."],
      "env": {"KEY": "value"}
    }
  }
}
```

### `.mcp-gateway-rules.json`
Gateway-specific access control rules defining which agents can access which servers and tools.

**Example files:**
- `.mcp-gateway-rules.json.example` - Example configuration with best practices
- Copy example to `.mcp-gateway-rules.json` and customize for your needs

## Default Agent Pattern

The **"default" agent** is a special fallback agent used when no explicit `agent_id` is provided.

### When "default" is Used

The gateway resolves agent identity in this order (highest priority first):

1. **Explicit `agent_id` parameter** in tool calls
2. **`GATEWAY_DEFAULT_AGENT`** environment variable
3. **"default" agent** in `.mcp-gateway-rules.json`
4. **Error** if none of the above and `deny_on_missing_agent: true`

### The `deny_on_missing_agent` Setting

This setting controls whether the gateway uses the fallback chain when `agent_id` is not provided:

**When `true` (Strict Mode):**
- Immediately rejects tool calls without `agent_id`
- Bypasses the fallback chain entirely, even if configured
- Effectively makes `agent_id` a required parameter
- Use in production multi-agent environments requiring explicit agent identification

**When `false` (Fallback Mode):**
- Uses the fallback chain described above
- Access is never implicitly granted - uses the fallback agent's explicit permissions
- Still rejects requests with helpful error if no fallback is configured
- Use in single-agent deployments or development environments for convenience

This flexibility allows different behaviors for different projects (e.g., `false` in development, `true` in production).

### Security Best Practice

**Always configure "default" to deny all access**, then grant specific permissions only to named agents. This follows the principle of least privilege.

```json
{
  "agents": {
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

**Why deny-all for "default"?**
- Prevents accidental access when `agent_id` is not provided
- Forces explicit agent configuration for any access
- Reduces attack surface in misconfiguration scenarios
- Makes permissions explicit and auditable

### Single-Agent Mode

For development or single-agent deployments, you can bypass per-agent access control:

**Option 1: Environment Variable**
```bash
export GATEWAY_DEFAULT_AGENT=developer
```

**Option 2: Configure "default" with permissions**
```json
{
  "agents": {
    "default": {
      "allow": {
        "servers": ["*"],
        "tools": {"*": ["*"]}
      }
    }
  }
}
```

### Example Progression

The example configuration demonstrates a permission progression:

1. **default** - No access (secure starting point)
2. **researcher** - Limited to read-only search tools
3. **backend** - Database and filesystem access with write protection
4. **admin** - Full access to all servers and tools

## Configuration Validation

Validate your configuration before deployment:

```bash
# Using the gateway's built-in validator (M3 milestone)
uv run python -m agent_mcp_gateway.cli validate

# Manual JSON validation
python -c "import json; json.load(open('.mcp-gateway-rules.json'))"
```

## Environment Variables

Configuration file locations can be customized:

```bash
GATEWAY_MCP_CONFIG=.mcp.json                    # Default: .mcp.json, fallback: ./config/.mcp.json
GATEWAY_RULES=.mcp-gateway-rules.json           # Default: .mcp-gateway-rules.json, fallback: ./config/.mcp-gateway-rules.json
GATEWAY_DEFAULT_AGENT=developer                 # Default agent when agent_id not provided
```

## Security: Rules File Location

The location of your gateway rules file has important security implications:

### Context Optimization Only
If you use the gateway only for context window optimization (not access control), in-project storage is fine:
```bash
.mcp-gateway-rules.json  # In project directory
```

### Access Control and Security
If you use gateway rules for actual access control, store them **outside the project directory**:

```bash
# Secure: Store rules outside project
export GATEWAY_RULES=~/.claude/mcp-gateway-rules.json
```

**Why this matters:**
- Coding agents can read files in the project directory
- Agents can inspect permission structures and identify privileged agent names
- Agents might attempt to modify rules to grant themselves more access
- External storage prevents these security risks

**Recommendation:** For production deployments or security-critical access control, always use an external rules file location.

## See Also

- `docs/quickstart-config.md` - Quick start guide for configuration
- `docs/specs/PRD.md` - Complete product requirements
- `CLAUDE.md` - Project overview and development guide
