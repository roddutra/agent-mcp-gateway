# Configuration Module

The configuration module (`src/config.py`) provides robust loading, validation, and management of configuration files for the Agent MCP Gateway.

## Features

- **MCP Server Configuration**: Load and validate MCP server definitions (stdio and HTTP transports)
- **Gateway Rules**: Load and validate agent policy configurations
- **Environment Variable Substitution**: Automatic `${VAR}` pattern replacement
- **Comprehensive Validation**: Type checking, required field validation, and cross-validation
- **Clear Error Messages**: Helpful, actionable error messages for all validation failures
- **Path Expansion**: Automatic `~/` home directory expansion

## Functions

### `load_mcp_config(path: str) -> dict`

Loads and validates MCP server configuration from a JSON file.

**Features:**
- Validates stdio transport (command, args, env)
- Validates HTTP transport (url, headers)
- Performs environment variable substitution
- Validates required fields per transport type
- Expands user paths (`~/`)

**Example:**
```python
from src.config import load_mcp_config

config = load_mcp_config("./config/.mcp.json")
servers = config["mcpServers"]
```

### `load_gateway_rules(path: str) -> dict`

Loads and validates gateway rules configuration from a JSON file.

**Features:**
- Validates agent policy structure
- Supports hierarchical agent names (`team.role`)
- Validates wildcard patterns (`*`, `get_*`, `*_query`)
- Validates allow/deny rules
- Expands user paths (`~/`)

**Example:**
```python
from src.config import load_gateway_rules

rules = load_gateway_rules(".mcp-gateway-rules.json")
agents = rules["agents"]
```

### `validate_rules_against_servers(rules: dict, mcp_config: dict) -> list[str]`

Cross-validates that all servers referenced in rules exist in the MCP configuration.

**Returns:** List of warning messages (empty if all valid)

**Example:**
```python
from src.config import load_mcp_config, load_gateway_rules, validate_rules_against_servers

mcp_config = load_mcp_config("./config/.mcp.json")
rules = load_gateway_rules(".mcp-gateway-rules.json")

warnings = validate_rules_against_servers(rules, mcp_config)
for warning in warnings:
    print(f"Warning: {warning}")
```

### `get_config_path(env_var: str, default: str) -> str`

Gets configuration file path from environment variable or uses default.

**Example:**
```python
from src.config import get_config_path

mcp_config_path = get_config_path(
    "GATEWAY_MCP_CONFIG",
    "./config/.mcp.json"
)
```

## Configuration File Formats

### MCP Servers Configuration

**File:** `config/.mcp.json`

**Structure:**
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "package-name"],
      "env": {
        "VAR_NAME": "${ENV_VAR}"
      }
    }
  }
}
```

**Stdio Transport:**
```json
{
  "server-name": {
    "command": "npx",           // Required
    "args": ["--flag", "value"], // Optional
    "env": {"KEY": "value"}     // Optional
  }
}
```

**HTTP Transport:**
```json
{
  "server-name": {
    "url": "https://example.com/mcp",  // Required
    "headers": {                        // Optional
      "Authorization": "Bearer token"
    }
  }
}
```

### Gateway Rules Configuration

**File:** `.mcp-gateway-rules.json`

**Structure:**
```json
{
  "agents": {
    "agent-id": {
      "allow": {
        "servers": ["server1", "server2"],
        "tools": {
          "server1": ["tool1", "tool2", "get_*"],
          "server2": ["*"]
        }
      },
      "deny": {
        "tools": {
          "server1": ["drop_*", "delete_*"]
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
- `*` - Matches all (must be alone)
- `get_*` - Matches prefix
- `*_query` - Matches suffix
- Middle wildcards NOT supported (`get_*_all` is invalid)

**Hierarchical Agent Names:**
- `researcher` - Simple name
- `team.researcher` - Hierarchical (team.role)
- `company.team.developer` - Multi-level hierarchy

## Environment Variables

### Configuration Paths

- `GATEWAY_MCP_CONFIG` - Path to MCP servers config (default: `./config/.mcp.json`)
- `GATEWAY_RULES` - Path to gateway rules config (default: `.mcp-gateway-rules.json`, fallback: `./config/.mcp-gateway-rules.json`)

### Variable Substitution

Environment variables in configuration files are substituted using `${VAR}` syntax:

```json
{
  "env": {
    "API_KEY": "${BRAVE_API_KEY}",
    "DATABASE_URL": "${POSTGRES_URL}"
  }
}
```

**Important:** All referenced environment variables MUST be set before loading the configuration, or a `ValueError` will be raised with a clear error message.

## Error Handling

The configuration module provides clear, actionable error messages for all validation failures:

### Missing File
```
FileNotFoundError: MCP server configuration file not found: /path/to/config.json
```

### Invalid JSON
```
JSONDecodeError: Invalid JSON in MCP server configuration: Expecting ',' delimiter
```

### Missing Environment Variable
```
ValueError: Environment variable "BRAVE_API_KEY" referenced in configuration but not set. 
Please set this variable before starting the gateway.
```

### Invalid Transport
```
ValueError: Server "my-server" must specify either "command" (stdio) or "url" (HTTP) transport
```

### Invalid Wildcard
```
ValueError: Agent "test" allow.tools["server"][0]: wildcard in pattern "get_*_all" 
must be at start, end, or alone
```

## Validation Script

Use the included validation script to check your configurations:

```bash
# Validate with default paths
python validate_config.py

# Validate with custom paths
GATEWAY_MCP_CONFIG=./my-config.json \
GATEWAY_RULES=./.mcp-gateway-rules.json \
python validate_config.py

# Validate with required environment variables
BRAVE_API_KEY=your_key \
POSTGRES_URL=postgresql://localhost/db \
python validate_config.py
```

## Testing

Run the test suite to verify the configuration module:

```bash
python test_config.py
```

**Tests cover:**
- Valid configuration loading
- Environment variable substitution
- Missing environment variables
- HTTP and stdio transports
- Invalid transport specifications
- Gateway rules validation
- Hierarchical agent names
- Wildcard pattern validation
- Cross-validation between rules and servers
- Config path resolution
- File not found errors
- Invalid JSON handling

## Usage Example

```python
import os
from src.config import (
    load_mcp_config,
    load_gateway_rules,
    validate_rules_against_servers,
    get_config_path
)

# Set required environment variables
os.environ["BRAVE_API_KEY"] = "your_api_key"
os.environ["POSTGRES_URL"] = "postgresql://localhost/db"

# Get config paths
mcp_config_path = get_config_path(
    "GATEWAY_MCP_CONFIG",
    "./config/.mcp.json"
)
rules_path = get_config_path(
    "GATEWAY_RULES",
    ".mcp-gateway-rules.json"
)

# Load configurations
try:
    mcp_config = load_mcp_config(mcp_config_path)
    rules = load_gateway_rules(rules_path)
    
    # Cross-validate
    warnings = validate_rules_against_servers(rules, mcp_config)
    if warnings:
        for warning in warnings:
            print(f"Warning: {warning}")
    
    print(f"Loaded {len(mcp_config['mcpServers'])} servers")
    print(f"Loaded {len(rules['agents'])} agent policies")
    
except FileNotFoundError as e:
    print(f"Configuration file not found: {e}")
except ValueError as e:
    print(f"Configuration validation error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Best Practices

1. **Use `.env.example`**: Document all required environment variables in `.env.example`
2. **Validate Early**: Run `validate_config.py` before starting the gateway
3. **Cross-Validate**: Always run `validate_rules_against_servers()` to catch undefined server references
4. **Secure Secrets**: Never commit actual API keys or credentials to version control
5. **Clear Naming**: Use descriptive server and agent names
6. **Wildcard Safety**: Use specific patterns (e.g., `get_*`) instead of `*` when possible
7. **Deny-Before-Allow**: Place deny rules before allow rules for clarity (enforced at runtime)

## Implementation Details

### Environment Variable Substitution

The `_substitute_env_vars()` function recursively processes all strings in the configuration:

- **Pattern:** `${VARIABLE_NAME}`
- **Behavior:** Replaces with `os.environ["VARIABLE_NAME"]`
- **Error:** Raises `ValueError` if variable not set
- **Recursive:** Processes nested dicts and lists

### Validation Order

1. **File existence** - Check file exists
2. **JSON parsing** - Parse JSON structure
3. **Structure validation** - Validate top-level keys
4. **Type validation** - Check all field types
5. **Transport validation** - Validate stdio/HTTP requirements
6. **Pattern validation** - Validate wildcards
7. **Environment substitution** - Replace ${VAR} patterns
8. **Cross-validation** - Validate references between configs

### Path Handling

All file paths are:
1. Expanded (`~/` → home directory)
2. Resolved to absolute paths
3. Validated for existence
4. Reported in error messages with full paths

This ensures consistent behavior across different execution contexts and clear error reporting.
