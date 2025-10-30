# Configuration Quick Start Guide

This guide will help you set up and validate your Agent MCP Gateway configuration.

## Step 1: Set Up Environment Variables

Copy the example environment file and customize it:

```bash
cp .env.example .env
```

Edit `.env` and set your actual values:

```bash
# Required for brave-search server
BRAVE_API_KEY=your_actual_brave_api_key

# Required for postgres server
POSTGRES_URL=postgresql://user:password@localhost:5432/database
```

**Load environment variables:**

```bash
# Option 1: Source the file
source .env

# Option 2: Use with commands
export $(cat .env | xargs)
```

## Step 2: Review Configuration Files

### MCP Servers Configuration

Edit `.mcp.json` (or `config/.mcp.json`) to define your MCP servers:

**Note:** `.mcp.json` is the standard MCP configuration file format used by Claude Code and other coding agents. If you already have a `.mcp.json` file in your development environment, the gateway can use it directly.

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "${BRAVE_API_KEY}"
      }
    }
  }
}
```

**Transport Types:**

- **stdio:** Use `command`, `args`, and optional `env`
- **HTTP:** Use `url` and optional `headers`

### Gateway Rules Configuration

Edit `config/gateway-rules.json` to define agent policies:

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
    }
  },
  "defaults": {
    "deny_on_missing_agent": true
  }
}
```

**Wildcard Patterns:**
- `"*"` - All tools
- `"get_*"` - All tools starting with `get_`
- `"*_query"` - All tools ending with `_query`

## Step 3: Validate Configuration

Run the validation script:

```bash
python validate_config.py
```

**Expected output for valid configuration:**

```
Agent MCP Gateway - Configuration Validator

MCP Servers Config: /path/to/.mcp.json
Gateway Rules: /path/to/config/gateway-rules.json

Loading MCP server configuration...
✓ Loaded 3 server(s):
  - brave-search (stdio)
  - postgres (stdio)
  - filesystem (stdio)

Loading gateway rules...
✓ Loaded 3 agent policy(ies):
  - researcher
  - backend
  - admin

Cross-validating rules against servers...
✓ All rules reference valid servers

✓ Configuration is valid and ready to use!
```

## Step 4: Use in Your Code

```python
import os
from src.config import (
    load_mcp_config,
    load_gateway_rules,
    validate_rules_against_servers,
    get_config_path
)

# Ensure environment variables are set
# (or load from .env using python-dotenv)

# Get configuration paths
# Default checks .mcp.json in current dir, then ./config/.mcp.json
mcp_config_path = get_config_path(
    "GATEWAY_MCP_CONFIG",
    ".mcp.json"
)
rules_path = get_config_path(
    "GATEWAY_RULES",
    "./config/gateway-rules.json"
)

# Load configurations
mcp_config = load_mcp_config(mcp_config_path)
rules = load_gateway_rules(rules_path)

# Validate cross-references
warnings = validate_rules_against_servers(rules, mcp_config)
if warnings:
    for warning in warnings:
        print(f"Warning: {warning}")

# Use configurations
servers = mcp_config["mcpServers"]
agents = rules["agents"]
```

## Common Issues

### Issue: Missing Environment Variable

**Error:**
```
ValueError: Environment variable "BRAVE_API_KEY" referenced in configuration 
but not set. Please set this variable before starting the gateway.
```

**Solution:**
```bash
export BRAVE_API_KEY=your_api_key
```

### Issue: Server Not Found

**Error:**
```
Warning: Agent "researcher" allow.servers references undefined server "unknown-server"
```

**Solution:**
Add the server to `.mcp.json` or remove the reference from gateway rules.

### Issue: Invalid JSON

**Error:**
```
JSONDecodeError: Invalid JSON in MCP server configuration: Expecting ',' delimiter
```

**Solution:**
Check your JSON syntax. Common issues:
- Missing commas between objects
- Trailing commas (not allowed in strict JSON)
- Unquoted keys or values
- Unescaped quotes in strings

### Issue: Invalid Wildcard Pattern

**Error:**
```
ValueError: Agent "test" allow.tools["server"][0]: wildcard in pattern "get_*_all" 
must be at start, end, or alone
```

**Solution:**
Use valid wildcard patterns:
- ✓ `"*"`
- ✓ `"get_*"`
- ✓ `"*_query"`
- ✗ `"get_*_all"` (wildcard in middle)

## Testing Your Configuration

Run the test suite to ensure everything works:

```bash
python test_config.py
```

All tests should pass:
```
✓ Valid MCP config test passed
✓ Environment variable substitution test passed
✓ Missing environment variable error test passed
...
✓ All tests passed!
```

## Next Steps

1. **Review** `src/CONFIG_README.md` for detailed documentation
2. **Customize** agent policies in `config/gateway-rules.json`
3. **Add** more MCP servers to `.mcp.json`
4. **Integrate** the configuration module into the gateway server

**Tip:** If you're using Claude Code or other coding agents that use `.mcp.json`, you can reuse that file directly with the gateway!

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_MCP_CONFIG` | `.mcp.json` (fallback: `./config/.mcp.json`) | Path to MCP servers config |
| `GATEWAY_RULES` | `./config/gateway-rules.json` | Path to gateway rules config |
| `BRAVE_API_KEY` | *(required)* | API key for Brave Search |
| `POSTGRES_URL` | *(required)* | PostgreSQL connection URL |

## Additional Resources

- **MCP Server Documentation:** https://modelcontextprotocol.io
- **FastMCP Documentation:** https://github.com/jlowin/fastmcp
- **Project PRD:** `docs/specs/PRD.md`
- **FastMCP Implementation Guide:** `docs/fastmcp-implementation-guide.md`
