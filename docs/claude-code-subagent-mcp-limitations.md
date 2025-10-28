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

## Proposed Workaround: Agent Name Convention

### Overview

Establish a convention where each agent/subagent explicitly passes its identity as an `agent_name` argument in all MCP tool calls.

### Implementation

#### 1. Configure Agents to Self-Identify

In each subagent definition (`.claude/agents/*.md`):

```yaml
---
name: front-end-developer
description: Frontend development specialist
tools: [your-mcp-tool]
---

You are a frontend development specialist.

**CRITICAL**: When calling ANY MCP tool, you MUST include an "agent_name" parameter set to "front-end-developer".

Example tool call format:
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments: {
      "some_argument": "value"
    },
    "agent_name": "front-end",
  }
}

Never make tool calls without the agent_name parameter.
```

#### 2. MCP Server Implementation

Your MCP server receives the `agent_name` and uses it for:

**Dynamic Tool Filtering:**
```python
def list_tools(agent_name: str = None):
    """Return tools based on agent identity"""
    all_tools = get_all_tools()
    
    if agent_name:
        config = load_agent_config(agent_name)
        allowed_tools = config.get('allowed_tools', [])
        return [t for t in all_tools if t.name in allowed_tools]
    
    return all_tools
```

**Context-Aware Behaviour:**
```python
def execute_tool(tool_name: str, agent_name: str = None, **kwargs):
    """Execute tool with agent-specific logic"""
    
    if tool_name == "search_database":
        if agent_name == "front-end":
            # Return UI-focused results
            return search_with_filters(ui_components=True)
        elif agent_name == "back-end":
            # Return API-focused results
            return search_with_filters(api_endpoints=True)
    
    return default_execution(tool_name, **kwargs)
```

**Access Control:**
```python
def validate_access(tool_name: str, agent_name: str):
    """Check if agent is allowed to use tool"""
    config = load_agent_config(agent_name)
    
    if tool_name not in config.get('allowed_tools', []):
        raise PermissionError(f"Agent '{agent_name}' not authorized for '{tool_name}'")
```

#### 3. Configuration File Example

`~/.config/mcp-server/agent-permissions.yaml`:

```yaml
agents:
  front-end:
    allowed_tools:
      - search_components
      - get_ui_examples
      - validate_css
    restricted_tools:
      - database_query
      - deploy_service
      
  back-end:
    allowed_tools:
      - database_query
      - api_documentation
      - deploy_service
    restricted_tools:
      - search_components
      
  security-reviewer:
    allowed_tools:
      - scan_vulnerabilities
      - audit_code
      - security_reports
    # Has access to all tools for review purposes
```

## Benefits

- **Agent-Specific Behaviour**: Return different data based on agent role
- **Access Control**: Restrict sensitive tools to specific agents
- **Audit Trail**: Log which agent performed which actions
- **Configuration-Driven**: Easy to modify permissions without code changes
- **Testing**: Can simulate different agents in development

## Limitations

- **Relies on LLM Compliance**: Agent must follow instructions to include `agent_name`
- **Not Cryptographically Secure**: Agent name can be spoofed (it's just a parameter)
- **Instruction Overhead**: Every agent config needs the reminder
- **No Enforcement**: Can't guarantee the parameter is always included

## Mitigation Strategies

1. **Validation**: MCP server should validate `agent_name` exists and is recognized
2. **Default Behaviour**: If `agent_name` is missing, use most restrictive permissions
3. **Logging**: Log all tool calls to detect missing or suspicious `agent_name` values
4. **Testing**: Write tests that verify agents include `agent_name` in tool calls

## Example: Complete Flow

1. User creates `front-end` subagent with instruction to always pass `agent_name: "front-end"`
2. Claude Code invokes the subagent for a task
3. Subagent calls MCP tool: `search_database(query="button", agent_name="front-end")`
4. MCP server receives call, extracts `agent_name: "front-end"`
5. MCP server checks config: front-end agent allowed to use `search_database`
6. MCP server applies front-end-specific filters (UI components only)
7. Returns filtered results optimised for frontend work

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
      "agent_name": "front-end",
      "agent_type": "subagent",
      "session_id": "abc123"
    }
  }
}
```

This would eliminate reliance on LLM instruction-following and provide cryptographic verification.

## Conclusion

While Claude Code doesn't natively support subagent identification in MCP calls, the `agent_name` parameter convention provides a practical workaround. It enables dynamic tool filtering, access control, and agent-specific behaviour whilst remaining simple to implement and configure.

The approach trades some security guarantees for immediate practicality, making it suitable for trusted environments and internal tooling where the benefits of agent-aware MCP servers outweigh the limitations.
