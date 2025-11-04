# Security Guide for Agent MCP Gateway

This guide covers security considerations when deploying the Agent MCP Gateway, including rules file location strategies, debug mode security, and best practices for production deployments.

---

## Table of Contents

- [Overview](#overview)
- [Rules File Location for Access Control](#rules-file-location-for-access-control)
- [Debug Mode and Gateway Status Tool](#debug-mode-and-gateway-status-tool)
- [Agent Impersonation Risks](#agent-impersonation-risks)
- [Production Best Practices](#production-best-practices)

---

## Overview

The security posture of your gateway deployment depends on **how you use it**:

- **Context Optimization Only:** Using the gateway purely to reduce token usage by loading tools on-demand
- **Access Control:** Using the gateway to restrict which agents can access which servers and tools

The configuration location and debug settings should reflect your use case.

---

## Rules File Location for Access Control

### Context Optimization Only

If you use the gateway **only for context window optimization** (reducing token usage by loading tools on-demand) and all agents should have similar access, the rules file can safely reside in your project directory:

```bash
# In project directory - visible to coding agents
.mcp-gateway-rules.json
```

This is convenient for:
- Single-agent deployments
- Development environments
- Scenarios where all agents have equivalent access
- Teams sharing a common permission set

### Access Control and Security

If you use the gateway **for actual access control** (restricting which agents can access which servers/tools), storing rules in the project directory creates security risks:

**Security Risks:**
- Coding agents (like Claude Code) can **read the rules file** and understand the permission structure
- Agents can **identify other agent identities** with higher privileges and attempt impersonation
- Agents might **attempt to modify the rules file** to grant themselves additional permissions
- The permission structure becomes visible to all agents working with the code

**Secure Configuration:**

Store the rules file **outside the project directory** and reference it via environment variable:

```bash
# Store rules outside project - not visible to coding agents
export GATEWAY_RULES=~/.claude/mcp-gateway-rules.json

# Or in a system-wide configuration directory
export GATEWAY_RULES=/etc/mcp-gateway/rules.json
```

**Benefits of External Rules Location:**
- Rules file is **not accessible** to coding agents working in the project
- Agents **cannot inspect** permission structures or identify privileged agent names
- Agents **cannot modify** access control rules
- Reduces attack surface for privilege escalation attempts
- Separates security policy from project code

**Example Secure Setup:**

```bash
# 1. Move rules file to secure location (outside project directory)
mv .mcp-gateway-rules.json ~/.claude/mcp-gateway-rules.json

# 2. Configure environment variable in your MCP client or shell
export GATEWAY_RULES=~/.claude/mcp-gateway-rules.json

# 3. Add gateway to your MCP client configuration
# See README Quick Start for examples
```

**Recommendation:** If your gateway rules are used for security-critical access control, always store them outside the project directory. If they're only used for context optimization convenience, in-project storage is acceptable.

---

## Debug Mode and Gateway Status Tool

The `get_gateway_status` tool provides comprehensive diagnostic information about the gateway's internal state, including:
- Hot reload status and timestamps
- PolicyEngine configuration details
- Available server names
- Configuration file paths

**Security Consideration:** In production environments, this diagnostic information could help coding agents understand the gateway's permission structure, identify privileged agent names, or map the infrastructure. Therefore, the `get_gateway_status` tool is **only available when debug mode is explicitly enabled**.

### Enabling Debug Mode

Debug mode can be enabled in two ways:

**Option 1: Environment Variable (Recommended for MCP clients)**

```bash
# Enable debug mode via environment variable
export GATEWAY_DEBUG=true

# Add to your MCP client configuration
{
  "mcpServers": {
    "agent-mcp-gateway": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/agent-mcp-gateway", "python", "main.py"],
      "env": {
        "GATEWAY_DEBUG": "true"
      }
    }
  }
}
```

**Option 2: CLI Flag (For direct execution)**

```bash
# Run gateway with debug mode
uv run python main.py --debug
```

### When to Enable Debug Mode

**Enable debug mode when:**
- Troubleshooting configuration issues
- Verifying hot reload functionality
- Debugging policy evaluation
- Local development and testing

**Disable debug mode when:**
- Running in production with security-sensitive access control
- Multiple agents with different privilege levels
- Rules file location is security-critical
- Agents should not inspect gateway internals

### Using get_gateway_status in Debug Mode

When debug mode is enabled, agents can check gateway health:

```python
# Check gateway status (only works with GATEWAY_DEBUG=true)
status = await client.call_tool("get_gateway_status", {
    "agent_id": "developer"
})

# Response includes:
# - reload_status: Hot reload timestamps and errors
# - policy_state: Number of agents and defaults
# - available_servers: List of server names
# - config_paths: Configuration file locations
```

**Note:** When debug mode is disabled (default), calling `get_gateway_status` will return an error indicating that the tool is not available. This prevents agents from accessing diagnostic information in production deployments.

---

## Agent Impersonation Risks

### The Risk

When agents can read the gateway rules file, they can:
1. **Discover privileged agent identities** (e.g., "admin", "backend", "database-admin")
2. **Understand permission boundaries** (what they can and cannot access)
3. **Attempt to impersonate** higher-privileged agents by passing different `agent_id` values

### Example Attack Vector

```json
// Agent reads .mcp-gateway-rules.json in project directory
{
  "agents": {
    "researcher": {
      "allow": {"servers": ["brave-search"]}
    },
    "admin": {
      "allow": {"servers": ["*"], "tools": {"*": ["*"]}}
    }
  }
}
```

The agent learns:
- An "admin" agent exists with full access
- It can try calling tools with `agent_id: "admin"` instead of its own identity

### Mitigation Strategies

**1. Store Rules Outside Project Directory (Primary Defense)**
```bash
export GATEWAY_RULES=~/.claude/mcp-gateway-rules.json
```

**2. Use Descriptive but Non-Obvious Agent Names**
```json
{
  "agents": {
    "user-12ab34cd": {},  // Better than "admin"
    "session-xyz789": {}   // Better than "backend-write"
  }
}
```

**3. Monitor Audit Logs for Suspicious Patterns**
```bash
# Watch for agents switching identities
grep "agent_id" logs/audit.jsonl | sort | uniq -c
```

**4. Use External Authentication**

In production, consider integrating with an identity provider that verifies agent identity before it reaches the gateway (future enhancement).

---

## Production Best Practices

### Configuration Management

**1. Separate Configuration from Code**
```bash
# Development - rules in project for convenience
.mcp-gateway-rules.json

# Production - rules in secure location
export GATEWAY_RULES=/etc/mcp-gateway/rules.json
```

**2. Use Environment-Specific Rules**
```bash
# Development environment
export GATEWAY_RULES=~/.config/mcp-gateway/dev-rules.json

# Staging environment
export GATEWAY_RULES=~/.config/mcp-gateway/staging-rules.json

# Production environment
export GATEWAY_RULES=/etc/mcp-gateway/prod-rules.json
```

**3. Version Control Strategy**
```bash
# Commit to git: Example rules showing structure
config/.mcp-gateway-rules.json.example

# Never commit: Actual rules with real agent identities
.mcp-gateway-rules.json  # Add to .gitignore
```

### Access Control Policies

**1. Principle of Least Privilege**

Grant minimum necessary permissions:
```json
{
  "agents": {
    "researcher": {
      "allow": {
        "servers": ["brave-search"],
        "tools": {"brave-search": ["brave_web_search"]}  // Specific tool
      }
    }
  }
}
```

Not:
```json
{
  "agents": {
    "researcher": {
      "allow": {
        "servers": ["*"],          // Too broad
        "tools": {"*": ["*"]}      // Grants everything
      }
    }
  }
}
```

**2. Use Deny Rules for Critical Operations**
```json
{
  "agents": {
    "backend": {
      "allow": {"servers": ["postgres"], "tools": {"postgres": ["*"]}},
      "deny": {"tools": {"postgres": ["drop_*", "truncate_*", "delete_*"]}}
    }
  }
}
```

**3. Default-Deny Policy**
```json
{
  "agents": {
    "default": {
      "deny": {"servers": ["*"]}
    }
  },
  "defaults": {
    "deny_on_missing_agent": true  // Require explicit agent_id
  }
}
```

### Monitoring and Auditing

**1. Enable Audit Logging**
```bash
# Gateway automatically logs to logs/audit.jsonl
tail -f logs/audit.jsonl
```

**2. Monitor for Anomalies**
```bash
# Unusual agent identities
jq '.agent_id' logs/audit.jsonl | sort | uniq -c

# Denied requests (possible probing)
jq 'select(.result == "denied")' logs/audit.jsonl

# High-privilege operations
jq 'select(.server == "postgres" and .tool | startswith("drop"))' logs/audit.jsonl
```

**3. Regular Access Reviews**

Periodically review:
- Which agents exist in your rules
- What permissions each agent has
- Whether any agents have excessive permissions
- Audit logs for unusual patterns

### Environment Variables Security

**1. Never Commit API Keys**
```bash
# Bad - hardcoded in .mcp.json
"env": {"BRAVE_API_KEY": "abc123"}

# Good - reference environment variable
"env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
```

**2. Use Secrets Management**
```bash
# For production, load from secrets manager
export BRAVE_API_KEY=$(aws secretsmanager get-secret-value --secret-id brave-api-key --query SecretString --output text)
```

**3. Separate Development and Production Secrets**
```bash
# Development - .env file (gitignored)
export BRAVE_API_KEY=dev_key_abc123

# Production - secrets manager or environment
export BRAVE_API_KEY=$(fetch-prod-secret brave-api-key)
```

### Deployment Checklist

Before deploying to production:

- [ ] Rules file stored outside project directory
- [ ] `GATEWAY_RULES` environment variable configured
- [ ] Debug mode disabled (`GATEWAY_DEBUG=false` or unset)
- [ ] Default-deny policy configured
- [ ] `deny_on_missing_agent: true` (require explicit agent_id)
- [ ] Audit logging enabled and monitored
- [ ] API keys in environment variables, not hardcoded
- [ ] All agents follow least-privilege principle
- [ ] Critical operations have explicit deny rules
- [ ] Regular audit log review scheduled

---

## Related Documentation

- [README.md - Quick Start](../README.md#quick-start)
- [README.md - Configuration](../README.md#configuration)
- [OAuth User Guide](oauth-user-guide.md)
- [Product Requirements Document](specs/PRD.md)

---

## Support

For security-related questions or to report vulnerabilities:
- GitHub Issues: [Create an issue](link-to-issues)
- Security Email: [security contact if available]

**Please do not disclose security vulnerabilities publicly until they have been addressed.**
