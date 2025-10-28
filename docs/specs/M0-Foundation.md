# Milestone 0: Foundation

**Status:** ✅ COMPLETE
**Target:** Basic gateway infrastructure with stdio transport and policy-aware server discovery
**Completed:** October 28, 2025

---

## Overview

M0 establishes the foundational infrastructure for the Agent MCP Gateway. This milestone focuses on creating a minimal viable gateway that can:
- Load configurations for downstream MCP servers and agent policies
- Expose the `list_servers` tool with policy-based filtering
- Support stdio transport for local development
- Implement basic audit logging

**Key Success Metric:** Agents can discover which servers they're allowed to access, reducing context from thousands of tokens to ~400 tokens for gateway tools.

---

## Core Components

### 1. Gateway Server Setup
### 2. Configuration Management
### 3. list_servers Tool
### 4. Audit Logging
### 5. Stdio Transport

---

## Detailed Task Checklist

### Project Structure Setup

- [x] Create project directory structure
  ```
  agent-mcp-gateway/
  ├── src/
  │   ├── __init__.py
  │   ├── gateway.py          # Main gateway server
  │   ├── config.py           # Configuration loading
  │   ├── policy.py           # Policy engine
  │   └── audit.py            # Audit logging
  ├── config/
  │   ├── mcp-servers.json    # Downstream server definitions
  │   └── gateway-rules.json  # Agent access policies
  ├── tests/
  │   └── __init__.py
  ├── pyproject.toml
  ├── main.py                 # Entry point
  └── README.md
  ```

- [x] Initialize uv project
  - [x] Run `uv init` if not already initialized
  - [x] Configure `pyproject.toml` with Python 3.12+ requirement
  - [x] Add FastMCP 2.13.0.1+ as dependency: `uv add "fastmcp>=2.13.0.1"`

### Configuration Loading (src/config.py)

- [x] Implement MCP server configuration loader
  - [x] Create `load_mcp_config(path: str) -> dict` function
  - [x] Support standard MCPConfig format with `mcpServers` key
  - [x] Handle both stdio (command, args, env) and HTTP (url, headers) transports
  - [x] Support environment variable substitution (e.g., `${BRAVE_API_KEY}`)
  - [x] Validate required fields per transport type
  - [x] Add helpful error messages for malformed configs

- [x] Implement gateway rules configuration loader
  - [x] Create `load_gateway_rules(path: str) -> dict` function
  - [x] Load agent policy definitions with allow/deny rules
  - [x] Validate rules structure (agents, defaults)
  - [x] Support wildcard patterns in tool names (`get_*`, `*`)
  - [x] Validate hierarchical agent names (`team.role`)

- [x] Add configuration validation
  - [x] Verify all referenced servers in rules exist in mcp-servers.json
  - [x] Warn about undefined agents if `deny_on_missing_agent` is false
  - [x] Check for conflicting rules within same agent

- [x] Environment variable support
  - [x] Support `GATEWAY_MCP_CONFIG` for server config path
  - [x] Support `GATEWAY_RULES` for rules config path
  - [x] Provide sensible defaults (./config/mcp-servers.json, ./config/gateway-rules.json)

**Code Reference:**
```python
# Expected usage pattern
from pathlib import Path
import json
import os

def load_mcp_config(path: str) -> dict:
    """Load and validate MCP server configuration."""
    config_path = Path(path).expanduser()
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Validate structure
    if "mcpServers" not in config:
        raise ValueError("Config must contain 'mcpServers' key")

    # Substitute environment variables
    config = _substitute_env_vars(config)

    return config

def _substitute_env_vars(obj):
    """Recursively substitute ${VAR} with environment variables."""
    # Implementation for env var substitution
    pass
```

**Documentation Reference:** FastMCP MCPConfig format - https://gofastmcp.com/servers/proxy#configuration-based-proxies

### Policy Engine (src/policy.py)

- [x] Implement policy evaluation engine
  - [x] Create `PolicyEngine` class with rules dictionary
  - [x] Implement `can_access_server(agent_id: str, server: str) -> bool`
  - [x] Implement `can_access_tool(agent_id: str, server: str, tool: str) -> bool`
  - [x] Support wildcard matching for tool names
  - [x] Implement deny-before-allow precedence

- [x] Policy precedence implementation (CRITICAL - DO NOT CHANGE)
  - [x] 1. Check explicit deny rules first
  - [x] 2. Check explicit allow rules second
  - [x] 3. Check wildcard deny rules third
  - [x] 4. Check wildcard allow rules fourth
  - [x] 5. Apply default policy last

- [x] Helper methods
  - [x] `get_allowed_servers(agent_id: str) -> list[str]`
  - [x] `get_allowed_tools(agent_id: str, server: str) -> list[str] | Literal["*"]`
  - [x] `get_policy_decision_reason(agent_id: str, operation: str) -> str`

**Code Reference:**
```python
class PolicyEngine:
    def __init__(self, rules: dict):
        self.rules = rules
        self.defaults = rules.get("defaults", {})

    def can_access_server(self, agent_id: str, server: str) -> bool:
        """Check if agent can access a server."""
        agent_rules = self.rules.get("agents", {}).get(agent_id)

        if not agent_rules:
            # Apply default policy
            return not self.defaults.get("deny_on_missing_agent", True)

        # Check deny rules first
        deny_servers = agent_rules.get("deny", {}).get("servers", [])
        if server in deny_servers:
            return False

        # Check allow rules
        allow_servers = agent_rules.get("allow", {}).get("servers", [])
        return server in allow_servers or "*" in allow_servers
```

### Gateway Server (src/gateway.py)

- [x] Create main gateway server class
  - [x] Initialize `FastMCP` instance with name "Agent MCP Gateway"
  - [x] Store mcp_config in server state via `set_state()`
  - [x] Store gateway_rules in server state via `set_state()`
  - [x] Store PolicyEngine instance in server state

- [x] Implement `list_servers` tool
  - [x] Add `@gateway.tool` decorator
  - [x] Require `agent_id: str` parameter
  - [x] Extract allowed servers from PolicyEngine
  - [x] Filter mcp_config servers to only those agent can access
  - [x] Return list of server info dicts with: name, transport type
  - [x] Support optional `include_metadata: bool` parameter
  - [x] Include server description if available in config

**Code Reference:**
```python
from fastmcp import FastMCP, Context

gateway = FastMCP(name="Agent MCP Gateway")

@gateway.tool
async def list_servers(agent_id: str, ctx: Context, include_metadata: bool = False) -> list[dict]:
    """
    List all MCP servers available to the calling agent based on policy rules.

    Args:
        agent_id: Identifier of the agent making the request
        include_metadata: Whether to include extended server metadata

    Returns:
        List of server information dicts
    """
    # Get configurations from context state
    policy_engine: PolicyEngine = ctx.get_state("policy_engine")
    mcp_config: dict = ctx.get_state("mcp_config")

    # Get servers this agent can access
    allowed_servers = policy_engine.get_allowed_servers(agent_id)
    all_servers = mcp_config.get("mcpServers", {})

    # Build response
    server_list = []
    for server_name in allowed_servers:
        if server_name in all_servers:
            server_config = all_servers[server_name]
            server_info = {
                "name": server_name,
                "transport": "stdio" if "command" in server_config else "http"
            }

            if include_metadata:
                server_info["description"] = server_config.get("description", "")
                # Add other metadata as needed

            server_list.append(server_info)

    return server_list
```

**Documentation Reference:**
- FastMCP Tools - https://gofastmcp.com/servers/tools
- FastMCP Server State - https://gofastmcp.com/servers/server

### Audit Logging (src/audit.py)

- [x] Implement audit logger
  - [x] Create `AuditLogger` class
  - [x] Support JSON-formatted log entries
  - [x] Include timestamp, agent_id, operation, decision, latency_ms
  - [x] Write to file (configurable path via env var)
  - [x] Support log rotation

- [x] Implement audit decorators/helpers
  - [x] `@audit_operation` decorator for tools
  - [x] Automatically capture operation start/end times
  - [x] Log policy decisions (ALLOW/DENY)
  - [x] Include rule that matched (for denials)

- [x] Define audit log schema
  ```json
  {
    "timestamp": "2025-10-28T10:30:00Z",
    "agent_id": "researcher",
    "operation": "list_servers",
    "decision": "ALLOW",
    "latency_ms": 12,
    "metadata": {}
  }
  ```

**Code Reference:**
```python
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

class AuditLogger:
    def __init__(self, log_path: str = "./logs/audit.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, agent_id: str, operation: str, decision: str,
            latency_ms: float, metadata: dict = None):
        """Log an audit entry."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": agent_id,
            "operation": operation,
            "decision": decision,
            "latency_ms": round(latency_ms, 2),
            "metadata": metadata or {}
        }

        with open(self.log_path, 'a') as f:
            f.write(json.dumps(entry) + "\n")
```

### Main Entry Point (main.py)

- [x] Create main entry point
  - [x] Load configurations from environment or defaults
  - [x] Initialize PolicyEngine with loaded rules
  - [x] Create gateway server instance
  - [x] Store configs and policy engine in gateway state
  - [x] Initialize AuditLogger
  - [x] Run gateway with stdio transport
  - [x] Handle graceful shutdown

**Code Reference:**
```python
import os
from src.gateway import gateway
from src.config import load_mcp_config, load_gateway_rules
from src.policy import PolicyEngine
from src.audit import AuditLogger

def main():
    # Load configurations
    mcp_config_path = os.getenv("GATEWAY_MCP_CONFIG", "./config/mcp-servers.json")
    rules_path = os.getenv("GATEWAY_RULES", "./config/gateway-rules.json")

    mcp_config = load_mcp_config(mcp_config_path)
    gateway_rules = load_gateway_rules(rules_path)

    # Initialize policy engine
    policy_engine = PolicyEngine(gateway_rules)

    # Initialize audit logger
    audit_logger = AuditLogger()

    # Store in gateway state
    gateway.set_state("mcp_config", mcp_config)
    gateway.set_state("gateway_rules", gateway_rules)
    gateway.set_state("policy_engine", policy_engine)
    gateway.set_state("audit_logger", audit_logger)

    # Run gateway with stdio transport (default)
    gateway.run()

if __name__ == "__main__":
    main()
```

### Example Configuration Files

- [x] Create example mcp-servers.json
  ```json
  {
    "mcpServers": {
      "brave-search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {
          "BRAVE_API_KEY": "${BRAVE_API_KEY}"
        }
      },
      "postgres": {
        "command": "uvx",
        "args": ["mcp-server-postgres"],
        "env": {
          "POSTGRES_URL": "${POSTGRES_URL}"
        }
      }
    }
  }
  ```

- [x] Create example gateway-rules.json
  ```json
  {
    "agents": {
      "researcher": {
        "allow": {
          "servers": ["brave-search"],
          "tools": {
            "brave-search": ["*"]
          }
        }
      },
      "backend": {
        "allow": {
          "servers": ["postgres"],
          "tools": {
            "postgres": ["query", "list_*"]
          }
        },
        "deny": {
          "tools": {
            "postgres": ["drop_*", "truncate_*"]
          }
        }
      }
    },
    "defaults": {
      "deny_on_missing_agent": true
    }
  }
  ```

### Testing

- [x] Create basic tests
  - [x] Test configuration loading
  - [x] Test policy engine with various scenarios
  - [x] Test list_servers tool with different agents
  - [x] Test audit logging captures events
  - [x] Test environment variable substitution

- [x] Create integration test
  - [x] Start gateway in test mode
  - [x] Connect client and call list_servers
  - [x] Verify correct servers returned for different agents
  - [x] Verify audit log entries created

**Code Reference:**
```python
# tests/test_policy.py
import pytest
from src.policy import PolicyEngine

def test_policy_deny_before_allow():
    rules = {
        "agents": {
            "test_agent": {
                "allow": {
                    "servers": ["postgres"],
                    "tools": {"postgres": ["*"]}
                },
                "deny": {
                    "tools": {"postgres": ["drop_*"]}
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    # Should allow query (in allow list)
    assert engine.can_access_tool("test_agent", "postgres", "query") is True

    # Should deny drop_table (in deny list, despite wildcard allow)
    assert engine.can_access_tool("test_agent", "postgres", "drop_table") is False
```

---

## Success Criteria

### Functional Requirements
- [x] Gateway loads and validates both configuration files
- [x] `list_servers` tool returns only servers agent can access
- [x] Policy engine correctly applies deny-before-allow precedence
- [x] Audit log captures all operations with correct data
- [x] Gateway runs via stdio transport

### Performance Requirements
- [x] `list_servers` responds in <50ms (P95)
- [x] Configuration loading completes in <200ms
- [x] No memory leaks during extended operation

### Quality Requirements
- [x] All code has type hints
- [x] Configuration validation provides clear error messages
- [x] Audit logs are properly formatted JSON
- [x] Example configs provided and tested

---

## Testing Approach

### Manual Testing
1. **Configuration Loading**
   ```bash
   # Test with valid config
   GATEWAY_MCP_CONFIG=./config/mcp-servers.json \
   GATEWAY_RULES=./config/gateway-rules.json \
   uv run python main.py

   # Test with invalid config (should show clear error)
   GATEWAY_MCP_CONFIG=./config/invalid.json \
   uv run python main.py
   ```

2. **list_servers Tool**
   ```python
   # Use FastMCP Client to test
   from fastmcp import Client

   async def test_list_servers():
       async with Client("main.py") as client:
           # As researcher agent
           result = await client.call_tool("list_servers", {
               "agent_id": "researcher"
           })
           print(result.data)  # Should show only brave-search

           # As backend agent
           result = await client.call_tool("list_servers", {
               "agent_id": "backend"
           })
           print(result.data)  # Should show only postgres
   ```

3. **Audit Logging**
   ```bash
   # After running gateway, check audit log
   cat ./logs/audit.jsonl
   # Verify entries exist with correct structure
   ```

### Automated Testing
```bash
# Run test suite
uv run pytest tests/

# Run with coverage
uv run pytest --cov=src tests/
```

---

## Dependencies

**External:**
- FastMCP 2.13.0.1+
- Python 3.12+
- uv package manager

**Internal:**
- None (this is the foundation milestone)

---

## Documentation References

- **FastMCP Server:** https://gofastmcp.com/servers/server
- **FastMCP Tools:** https://gofastmcp.com/servers/tools
- **FastMCP Proxy:** https://gofastmcp.com/servers/proxy
- **MCP Lifecycle:** https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
- **MCP Transports:** https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

---

## Notes

- This milestone does NOT include proxying to downstream servers yet - that comes in M1
- The gateway only exposes `list_servers` at this stage
- Focus is on getting the foundation right: config loading, policy engine, audit logging
- Stdio transport is sufficient for M0 - HTTP comes in M2
