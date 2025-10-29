# Validation Framework Usage Guide

## Quick Reference

The validation framework provides functions to validate configuration files before applying them to the gateway.

## Functions

### validate_mcp_config()

Validates MCP server configuration structure.

```python
from src.config import validate_mcp_config

config = {
    "mcpServers": {
        "brave-search": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"]
        }
    }
}

valid, error = validate_mcp_config(config)
if valid:
    print("Config is valid!")
else:
    print(f"Config error: {error}")
```

**Returns:**
- `(True, None)` if configuration is valid
- `(False, "error message")` if configuration is invalid

### validate_gateway_rules()

Validates gateway rules configuration structure.

```python
from src.config import validate_gateway_rules

rules = {
    "agents": {
        "researcher": {
            "allow": {
                "servers": ["brave-search"],
                "tools": {"brave-search": ["*"]}
            }
        }
    }
}

valid, error = validate_gateway_rules(rules)
if valid:
    print("Rules are valid!")
else:
    print(f"Rules error: {error}")
```

**Returns:**
- `(True, None)` if rules are valid
- `(False, "error message")` if rules are invalid

### reload_configs()

Loads and validates both configuration files in one call.

```python
from src.config import reload_configs

mcp_config, gateway_rules, error = reload_configs(
    "/path/to/mcp-servers.json",
    "/path/to/gateway-rules.json"
)

if error is None:
    # Both configs are valid
    print(f"Loaded {len(mcp_config['mcpServers'])} servers")
    print(f"Loaded {len(gateway_rules['agents'])} agents")
    # Now safe to apply configs to gateway
else:
    # Validation failed
    print(f"Config validation failed: {error}")
    # Do NOT apply configs
```

**Returns:**
- Success: `(mcp_config_dict, gateway_rules_dict, None)`
- Failure: `(None, None, error_message)`

**Important:** This function only validates - it does NOT apply configs to the running gateway.

### get_stored_config_paths()

Retrieves the paths of currently loaded configuration files.

```python
from src.config import get_stored_config_paths

mcp_path, rules_path = get_stored_config_paths()
if mcp_path and rules_path:
    print(f"MCP config: {mcp_path}")
    print(f"Gateway rules: {rules_path}")

    # Can now reload from stored paths
    from src.config import reload_configs
    mcp_config, gateway_rules, error = reload_configs(mcp_path, rules_path)
```

**Returns:**
- `(mcp_config_path, gateway_rules_path)` - Either or both may be None

## Common Patterns

### Pattern 1: Validate Before Apply

```python
from src.config import reload_configs

def hot_reload_configs(mcp_path, rules_path):
    """Safely reload and apply configuration changes."""
    # Step 1: Load and validate
    mcp_config, gateway_rules, error = reload_configs(mcp_path, rules_path)

    if error:
        print(f"Validation failed: {error}")
        return False

    # Step 2: Apply to gateway (your implementation)
    try:
        apply_configs_to_gateway(mcp_config, gateway_rules)
        print("Configs applied successfully")
        return True
    except Exception as e:
        print(f"Failed to apply configs: {e}")
        return False
```

### Pattern 2: Validate User Input

```python
from src.config import validate_mcp_config, validate_gateway_rules
import json

def validate_config_file(file_path, config_type):
    """Validate a configuration file before saving."""
    with open(file_path) as f:
        config = json.load(f)

    if config_type == "mcp":
        valid, error = validate_mcp_config(config)
    elif config_type == "rules":
        valid, error = validate_gateway_rules(config)
    else:
        return False, "Unknown config type"

    return valid, error
```

### Pattern 3: Reload from Stored Paths

```python
from src.config import get_stored_config_paths, reload_configs

def reload_current_configs():
    """Reload the currently active configuration files."""
    mcp_path, rules_path = get_stored_config_paths()

    if not mcp_path or not rules_path:
        print("No configs loaded yet")
        return None, None, "No configs loaded"

    return reload_configs(mcp_path, rules_path)
```

### Pattern 4: File Watcher Integration

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.config import reload_configs, get_stored_config_paths
import time

class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_reload = 0
        self.debounce_seconds = 1

    def on_modified(self, event):
        if event.is_directory:
            return

        # Debounce rapid changes
        now = time.time()
        if now - self.last_reload < self.debounce_seconds:
            return
        self.last_reload = now

        # Get current config paths
        mcp_path, rules_path = get_stored_config_paths()
        if not mcp_path or not rules_path:
            return

        # Reload and validate
        print(f"Config file changed: {event.src_path}")
        mcp_config, gateway_rules, error = reload_configs(mcp_path, rules_path)

        if error:
            print(f"Config validation failed: {error}")
            # Keep using old configs
        else:
            print("Config validated, applying changes...")
            # Apply new configs
            apply_configs_to_gateway(mcp_config, gateway_rules)

# Usage
handler = ConfigFileHandler()
observer = Observer()
observer.schedule(handler, "/path/to/configs", recursive=False)
observer.start()
```

## Error Handling

### MCP Config Errors

Common validation errors:

```python
# Missing mcpServers key
{"wrong_key": {}}
# Error: 'Missing required key "mcpServers"'

# Both command and url
{"mcpServers": {"srv": {"command": "npx", "url": "http://..."}}}
# Error: 'Server "srv" cannot have both "command" (stdio) and "url" (HTTP)...'

# Invalid URL format
{"mcpServers": {"srv": {"url": "ftp://example.com"}}}
# Error: 'Server "srv": "url" must start with http:// or https://...'

# Invalid args type
{"mcpServers": {"srv": {"command": "npx", "args": "should-be-array"}}}
# Error: 'Server "srv": "args" must be an array...'
```

### Gateway Rules Errors

Common validation errors:

```python
# Invalid agent ID
{"agents": {"agent@invalid": {...}}}
# Error: 'Agent ID "agent@invalid" contains invalid characters...'

# Invalid wildcard pattern
{"agents": {"test": {"allow": {"tools": {"db": ["get_*_all"]}}}}}
# Error: 'Agent "test" allow.tools["db"][0]: wildcard in pattern "get_*_all" must be at start, end, or alone'

# Invalid wildcard in server name
{"agents": {"test": {"allow": {"servers": ["db-*"]}}}}
# Error: 'Agent "test" allow.servers[0]: wildcard "*" can only be used alone...'
```

### Cross-Validation Errors

```python
# Rules reference undefined server
mcp_config = {"mcpServers": {"postgres": {...}}}
rules = {"agents": {"test": {"allow": {"servers": ["postgres", "nonexistent"]}}}}

_, _, error = reload_configs(mcp_path, rules_path)
# Error: 'Gateway rules reference undefined servers:
#   - Agent "test" allow.servers references undefined server "nonexistent"'
```

## Testing

### Unit Test Example

```python
import pytest
from src.config import validate_mcp_config

def test_valid_config():
    config = {
        "mcpServers": {
            "test": {"command": "npx"}
        }
    }
    valid, error = validate_mcp_config(config)
    assert valid is True
    assert error is None

def test_invalid_config():
    config = {"wrong_key": {}}
    valid, error = validate_mcp_config(config)
    assert valid is False
    assert "mcpServers" in error
```

### Integration Test Example

```python
import tempfile
import json
from pathlib import Path
from src.config import reload_configs

def test_reload_valid_configs():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create config files
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({
            "mcpServers": {"test": {"command": "npx"}}
        }))

        rules_file.write_text(json.dumps({
            "agents": {"test": {"allow": {"servers": ["test"]}}}
        }))

        # Reload and validate
        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )

        assert error is None
        assert "test" in mcp_config["mcpServers"]
        assert "test" in gateway_rules["agents"]
```

## Best Practices

1. **Always validate before applying:**
   ```python
   # Good
   mcp_config, gateway_rules, error = reload_configs(mcp_path, rules_path)
   if error is None:
       apply_configs(mcp_config, gateway_rules)

   # Bad - never load and apply without validation
   mcp_config = json.load(open(mcp_path))
   apply_configs(mcp_config, ...)  # Could break gateway!
   ```

2. **Handle all error cases:**
   ```python
   mcp_config, gateway_rules, error = reload_configs(mcp_path, rules_path)

   if error:
       if "not found" in error:
           # File doesn't exist
           log.error(f"Config file missing: {error}")
       elif "Invalid JSON" in error:
           # JSON syntax error
           log.error(f"JSON syntax error: {error}")
       else:
           # Validation error
           log.error(f"Config validation failed: {error}")
       return
   ```

3. **Use stored paths for reloading:**
   ```python
   # Good - uses stored paths
   mcp_path, rules_path = get_stored_config_paths()
   if mcp_path and rules_path:
       reload_configs(mcp_path, rules_path)

   # Bad - hardcoded paths
   reload_configs("/fixed/path/mcp.json", "/fixed/path/rules.json")
   ```

4. **Provide user feedback:**
   ```python
   mcp_config, gateway_rules, error = reload_configs(mcp_path, rules_path)

   if error:
       # Show specific error to user
       print(f"❌ Config validation failed:")
       print(f"   {error}")
       print(f"   Previous config still active")
   else:
       # Show success details
       print(f"✓ Config validated successfully:")
       print(f"   - {len(mcp_config['mcpServers'])} MCP servers")
       print(f"   - {len(gateway_rules['agents'])} agents")
   ```

## See Also

- [Validation Framework Summary](../VALIDATION_FRAMEWORK_SUMMARY.md) - Complete implementation details
- [Test Suite](../tests/test_validation_and_reload.py) - Comprehensive test examples
- [Demo Script](../tests/demo_validation.py) - Interactive demonstrations
