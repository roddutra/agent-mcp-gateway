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

**Note for GUI Applications (Claude Desktop, etc.):**
If using `${VAR_NAME}` syntax in `.mcp.json`, macOS GUI applications don't access shell environment variables. Add API keys to the gateway's `env` object in your MCP client configuration instead. See README.md "Environment Variables" section for details. (Not needed if you hardcode values in `.mcp.json` without `${VAR_NAME}` syntax.)

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

Edit `.mcp-gateway-rules.json` (or `config/.mcp-gateway-rules.json`) to define agent policies:

**Note:** `.mcp-gateway-rules.json` follows the same naming pattern as `.mcp.json` and is designed for version control and team sharing. All team members can use the same agent access policies by checking this file into your repository.

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

**Agent Identity Options:**

The gateway supports flexible agent identity with a fallback chain:

1. **Explicit agent_id in tool calls** (recommended for multi-agent setups)
2. **Environment variable** (`GATEWAY_DEFAULT_AGENT`) for single-agent mode
3. **"default" agent** in rules file (fallback when `deny_on_missing_agent` is false)

**The `deny_on_missing_agent` Setting:**
- **`true` (Strict Mode):** Rejects tool calls without `agent_id`, bypassing fallback chain - use in production multi-agent environments
- **`false` (Fallback Mode):** Uses the fallback chain above - use in single-agent/development environments

**Single-Agent Mode Example:**
```bash
export GATEWAY_DEFAULT_AGENT=researcher
uv run python main.py
# Now all tools work without passing agent_id explicitly
```

**Secure Default Agent:**
The "default" agent above denies all servers, following the principle of least privilege. This ensures requests without explicit agent identity are rejected safely unless you've configured a specific default via environment variable.

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
Gateway Rules: /path/to/.mcp-gateway-rules.json

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
    ".mcp-gateway-rules.json"
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
2. **Customize** agent policies in `.mcp-gateway-rules.json`
3. **Add** more MCP servers to `.mcp.json`
4. **Integrate** the configuration module into the gateway server

**Tip:** Both `.mcp.json` and `.mcp-gateway-rules.json` are designed for version control. Check them into your repository to ensure your entire team uses consistent MCP server configurations and agent access policies!

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_MCP_CONFIG` | `.mcp.json` (fallback: `./config/.mcp.json`) | Path to MCP servers config |
| `GATEWAY_RULES` | `.mcp-gateway-rules.json` (fallback: `./config/.mcp-gateway-rules.json`) | Path to gateway rules config |
| `GATEWAY_DEFAULT_AGENT` | *(none)* | Default agent when `agent_id` not provided (optional) |
| `GATEWAY_DEBUG` | `false` | Enable debug mode to expose `get_gateway_status` tool |
| `BRAVE_API_KEY` | *(required)* | API key for Brave Search |
| `POSTGRES_URL` | *(required)* | PostgreSQL connection URL |

## Additional Resources

- **MCP Server Documentation:** https://modelcontextprotocol.io
- **FastMCP Documentation:** https://github.com/jlowin/fastmcp
- **Project PRD:** `docs/specs/PRD.md`
- **FastMCP Implementation Guide:** `docs/fastmcp-implementation-guide.md`
