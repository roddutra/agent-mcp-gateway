# Claude Code Subagent Identification in MCP

## The Problem

**Claude Code does not currently pass subagent identity information to MCP servers when tools are invoked.**

### What This Means

- MCP servers cannot natively identify which agent or subagent is calling a tool
- All tool calls from any agent/subagent look identical to the MCP server
- No way to implement agent-specific behaviour or access control at the MCP server level

### MCP Protocol Limitations

The standard MCP tool call format (JSON-RPC 2.0) only includes:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": {
      // tool-specific arguments only
    }
  }
}
```

**No agent context, session ID, or caller identification is included.**

### Hooks Don't Help

Claude Code hooks (PreToolUse, PostToolUse) receive:
- `tool_name`: Name of the tool being invoked
- `tool_input`: Parameters passed to the tool

**But not:**
- Which agent/subagent initiated the call
- Agent configuration or identity
- Session or context information

While PreToolUse hooks can modify tool inputs, they don't have access to agent identity information to inject.

## Implemented Solution: Optional agent_id with Fallback Chain

### Overview

The Agent MCP Gateway implements an optional `agent_id` parameter with a secure fallback chain, providing flexibility for both multi-agent and single-agent workflows.

### Implementation

#### 1. Agent Identity Fallback Chain

The gateway resolves agent identity using the following priority:

1. **Explicit `agent_id` in tool call** (highest priority)
2. **`GATEWAY_DEFAULT_AGENT` environment variable**
3. **Agent named "default" in gateway rules** (if `deny_on_missing_agent` is false)
4. **Error** (if none configured and `deny_on_missing_agent` is true)

#### 2. Multi-Agent Setup (Explicit agent_id)

For multi-agent workflows, configure each subagent to pass its identity explicitly.

In each subagent definition (`.claude/agents/*.md`):

```yaml
---
name: front-end-developer
description: Frontend development specialist
tools: [your-mcp-tool]
---

You are a frontend development specialist.

**RECOMMENDED**: When calling ANY MCP tool, include an "agent_id" parameter set to your name, "front-end-developer", for explicit access control.

Example tool call format:
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": {
      "some_argument": "value",
      "agent_id": "front-end-developer"
    }
  }
}
```

#### 3. Single-Agent Setup (Environment Variable)

For single-agent workflows, use the `GATEWAY_DEFAULT_AGENT` environment variable:

```bash
export GATEWAY_DEFAULT_AGENT=developer
uv run python main.py
# All tool calls now use "developer" agent when agent_id is not provided
```

Gateway rules configuration:
```json
{
  "agents": {
    "developer": {
      "allow": {
        "servers": ["*"],
        "tools": {"*": ["*"]}
      }
    }
  },
  "defaults": {
    "deny_on_missing_agent": false
  }
}
```

#### 4. Gateway Implementation

The gateway receives the `agent_id` (or uses fallback) and applies it for:

**Dynamic Tool Filtering:**
```python
def list_tools(agent_id: str = None):
    """Return tools based on agent identity"""
    all_tools = get_all_tools()
    
    if agent_id:
        config = load_agent_config(agent_id)
        allowed_tools = config.get('allowed_tools', [])
        return [t for t in all_tools if t.name in allowed_tools]
    
    return all_tools
```

**Context-Aware Behaviour:**
```python
def execute_tool(tool_name: str, agent_id: str = None, **kwargs):
    """Execute tool with agent-specific logic"""
    
    if tool_name == "search_database":
        if agent_id == "front-end":
            # Return UI-focused results
            return search_with_filters(ui_components=True)
        elif agent_id == "back-end":
            # Return API-focused results
            return search_with_filters(api_endpoints=True)
    
    return default_execution(tool_name, **kwargs)
```

**Access Control:**
```python
def validate_access(tool_name: str, agent_id: str):
    """Check if agent is allowed to use tool"""
    config = load_agent_config(agent_id)
    
    if tool_name not in config.get('allowed_tools', []):
        raise PermissionError(f"Agent '{agent_id}' not authorized for '{tool_name}'")
```

#### 5. Configuration File Example

`.mcp-gateway-rules.json`:

```json
{
  "agents": {
    "front-end": {
      "allow": {
        "servers": ["browser", "ui-components"],
        "tools": {
          "browser": ["*"],
          "ui-components": ["search_*", "validate_*"]
        }
      },
      "deny": {
        "servers": ["database"]
      }
    },
    "back-end": {
      "allow": {
        "servers": ["database", "api-server"],
        "tools": {
          "database": ["query", "list_*"],
          "api-server": ["*"]
        }
      },
      "deny": {
        "tools": {
          "database": ["drop_*", "truncate_*"]
        }
      }
    },
    "security-reviewer": {
      "allow": {
        "servers": ["*"],
        "tools": {"*": ["*"]}
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

## Benefits

- **Agent-Specific Behaviour**: Return different data based on agent role
- **Access Control**: Restrict sensitive tools to specific agents
- **Audit Trail**: Log which agent performed which actions
- **Configuration-Driven**: Easy to modify permissions without code changes
- **Testing**: Can simulate different agents in development
- **Flexibility**: Support both single-agent and multi-agent workflows
- **Secure by Default**: Principle of least privilege with "default" agent fallback

## Limitations

- **Relies on LLM Compliance**: For explicit agent_id, agent must follow instructions
- **Not Cryptographically Secure**: Agent name can be spoofed (it's just a parameter)
- **Instruction Overhead**: Multi-agent setups need agent_id instructions in each config
- **Environment Variables**: Single-agent mode requires environment configuration

## Mitigation Strategies

1. **Validation**: Gateway validates `agent_id` exists in rules
2. **Fallback Chain**: Secure defaults when `agent_id` is missing
3. **Principle of Least Privilege**: "default" agent has minimal permissions
4. **Logging**: Audit all tool calls including agent identity resolution
5. **Testing**: Write tests that verify agent identity behavior
6. **Error Codes**: Clear error messages for fallback configuration issues

## Example: Complete Flow

### Multi-Agent Flow (Explicit agent_id)

1. User creates `front-end-developer` subagent with instruction to pass `agent_id: "front-end-developer"`
2. Claude Code invokes the subagent for a task
3. Subagent calls gateway tool: `get_server_tools(agent_id="front-end-developer", server="browser")`
4. Gateway receives call, extracts `agent_id: "front-end-developer"`
5. Gateway checks rules: front-end agent allowed to access "browser" server
6. Gateway returns filtered tool definitions for browser server
7. Subagent uses tools with front-end specific permissions

### Single-Agent Flow (Environment Variable)

1. Developer sets `GATEWAY_DEFAULT_AGENT=developer`
2. Developer starts gateway: `uv run python main.py`
3. Agent calls gateway tool without agent_id: `list_servers()`
4. Gateway applies fallback chain: uses "developer" from environment variable
5. Gateway checks rules: developer agent has full access (configured as `"*"`)
6. Gateway returns all available servers
7. Agent can use all tools without passing agent_id explicitly

## Future Improvements

**Ideal Solution**: Anthropic adds native agent context to MCP protocol:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": { ... },
    "agent_context": {
      "agent_id": "front-end-developer",
      "agent_type": "subagent",
      "session_id": "abc123"
    }
  }
}
```

This would eliminate reliance on LLM instruction-following and provide cryptographic verification.

## Conclusion

While Claude Code doesn't natively support subagent identification in MCP calls, the Agent MCP Gateway's optional `agent_id` parameter with secure fallback chain provides a flexible and practical solution. It enables:

- **Multi-agent workflows** with explicit agent identity and fine-grained access control
- **Single-agent workflows** with environment variable configuration for simplicity
- **Secure defaults** following the principle of least privilege
- **Dynamic tool filtering** based on agent role and permissions

The approach trades some security guarantees for immediate practicality, making it suitable for trusted environments and internal tooling where the benefits of agent-aware MCP servers outweigh the limitations. The fallback mechanism ensures that even when `agent_id` is not provided, access is never implicitly granted to all resources.
