# Validation Framework Implementation Summary

## Overview

This document summarizes the validation framework added to `src/config.py` for Phase 1 of the hot config reload feature.

## What Was Added

### 1. Validation Functions

#### `validate_mcp_config(config: dict) -> tuple[bool, Optional[str]]`

Validates MCP server configuration structure without loading from file.

**Validates:**
- Top-level structure (must be dict with "mcpServers" key)
- Each server must be a dict with either "command" or "url" (not both)
- Stdio transport validation:
  - `command` must be string
  - `args` must be array of strings
  - `env` must be dict with string values
- HTTP transport validation:
  - `url` must be string starting with http:// or https://
  - `headers` must be dict with string values

**Returns:**
- `(True, None)` if valid
- `(False, error_message)` if invalid with helpful error message

**Example:**
```python
config = {"mcpServers": {"test": {"command": "npx"}}}
valid, error = validate_mcp_config(config)
# Returns: (True, None)

config = {"wrong_key": {}}
valid, error = validate_mcp_config(config)
# Returns: (False, 'Missing required key "mcpServers"')
```

#### `validate_gateway_rules(rules: dict) -> tuple[bool, Optional[str]]`

Validates gateway rules configuration structure without loading from file.

**Validates:**
- Top-level structure (must be dict, can have "agents" and "defaults")
- Agent ID format (alphanumeric, dot, hyphen, underscore)
- Allow/deny sections structure
- Server lists (strings, wildcard "*" only alone)
- Tool patterns (strings, single wildcard at start/end/alone)
- Defaults section (deny_on_missing_agent must be boolean)

**Returns:**
- `(True, None)` if valid
- `(False, error_message)` if invalid with helpful error message

**Example:**
```python
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
# Returns: (True, None)

rules = {"agents": {"agent@invalid": {"allow": {}}}}
valid, error = validate_gateway_rules(rules)
# Returns: (False, 'Agent ID "agent@invalid" contains invalid characters...')
```

### 2. Reload Function

#### `reload_configs(mcp_config_path: str, gateway_rules_path: str) -> tuple[Optional[dict], Optional[dict], Optional[str]]`

Loads and validates both configuration files without applying them to the running system.

**Process:**
1. Loads MCP config from file
2. Validates MCP config structure
3. Loads gateway rules from file
4. Validates gateway rules structure
5. Cross-validates that servers referenced in rules exist in config

**Returns:**
- Success: `(mcp_config_dict, gateway_rules_dict, None)`
- Failure: `(None, None, error_message)`

**Important Notes:**
- Does NOT perform environment variable substitution (that's for `load_mcp_config()`)
- Does NOT apply configs to running system (just validates)
- Fails fast on first error encountered
- Includes cross-validation warnings in error message

**Example:**
```python
# Valid configs
mcp_config, gateway_rules, error = reload_configs(
    "/path/to/.mcp.json",
    "/path/to/.mcp-gateway-rules.json"
)
if error is None:
    print(f"Loaded {len(mcp_config['mcpServers'])} servers")
    print(f"Loaded {len(gateway_rules['agents'])} agents")
else:
    print(f"Validation failed: {error}")
```

### 3. Config Path Storage

#### Global Variables
```python
_mcp_config_path: Optional[str] = None
_gateway_rules_path: Optional[str] = None
```

Stores the absolute paths of loaded configs for future reloading.

#### `get_stored_config_paths() -> tuple[Optional[str], Optional[str]]`

Returns the stored config file paths.

**Returns:**
- `(mcp_config_path, gateway_rules_path)` - Either or both may be None

**Updated Functions:**
- `load_mcp_config()` now stores its path in `_mcp_config_path`
- `load_gateway_rules()` now stores its path in `_gateway_rules_path`

## Validation Details

### MCP Config Validation Rules

1. **Structure:**
   - Must be a JSON object
   - Must contain "mcpServers" key
   - "mcpServers" must be an object

2. **Server Configuration:**
   - Each server must be an object
   - Must have either "command" (stdio) OR "url" (HTTP), not both
   - Must not have neither

3. **Stdio Transport:**
   - "command": string (required)
   - "args": array of strings (optional)
   - "env": object with string values (optional)

4. **HTTP Transport:**
   - "url": string starting with http:// or https:// (required)
   - "headers": object with string values (optional)

### Gateway Rules Validation Rules

1. **Structure:**
   - Must be a JSON object
   - Can contain "agents" and/or "defaults"

2. **Agent Configuration:**
   - Agent IDs: non-empty strings, alphanumeric + dot/hyphen/underscore
   - Each agent must be an object
   - Can have "allow" and/or "deny" sections

3. **Allow/Deny Sections:**
   - Must be objects
   - Can contain "servers" (array) and/or "tools" (object)

4. **Servers List:**
   - Array of strings
   - Wildcard "*" can only be used alone (not "db-*")

5. **Tools Mapping:**
   - Object with server names as keys
   - Values are arrays of string patterns
   - Wildcard rules:
     - Only one "*" per pattern
     - Must be alone ("*") or at start ("get_*") or end ("*_query")
     - Cannot be in middle ("get*data") or multiple ("get_*_all")

6. **Defaults Section:**
   - Must be an object
   - "deny_on_missing_agent" must be boolean

### Cross-Validation

The `reload_configs()` function performs cross-validation using the existing `validate_rules_against_servers()` function:

- Checks that all servers referenced in rules exist in MCP config
- Checks both "allow.servers" and "deny.servers"
- Checks all servers in "allow.tools" and "deny.tools"
- Wildcard "*" is allowed (matches any server)
- Returns descriptive error if undefined servers found

## Edge Cases Handled

1. **Empty but valid configs:**
   - `{"mcpServers": {}}` is valid (no servers configured)
   - `{"agents": {}}` is valid (no agents configured)

2. **Complex wildcard patterns:**
   - Multiple patterns per server: `["*", "get_*", "*_query", "list_*"]` ✓
   - Multiple wildcards in pattern: `["get_*_all"]` ✗

3. **Hierarchical agent names:**
   - Dot notation: `"team.backend"`, `"team.frontend"` ✓
   - Underscore: `"org_admin"` ✓
   - Hyphen: `"sub-agent"` ✓
   - Special chars: `"agent@invalid"` ✗

4. **Path expansion:**
   - Handles `~` for home directory
   - Converts relative paths to absolute
   - Validates file existence before loading

5. **JSON syntax errors:**
   - Returns clear error with position info
   - Distinguishes between file not found, JSON syntax, and validation errors

6. **Cross-validation warnings:**
   - Lists all undefined servers (not just first)
   - Provides agent ID and section context
   - Formatted for easy debugging

## Testing

### Test Coverage

**Total Tests:** 96 (43 existing + 53 new)
- **43 existing tests:** All pass unchanged (validates backward compatibility)
- **53 new tests:** Comprehensive validation and reload testing

**New Test File:** `tests/test_validation_and_reload.py`

**Test Categories:**
1. `TestValidateMCPConfig` (19 tests)
   - Valid configs (minimal, with args, with env, HTTP, with headers)
   - Invalid structure (missing key, wrong types)
   - Invalid transport (both, neither, invalid values)
   - Invalid field types (command, args, env, url, headers)

2. `TestValidateGatewayRules` (22 tests)
   - Valid rules (minimal, with tools, with deny, with defaults, hierarchical)
   - Invalid structure (wrong types, missing fields)
   - Invalid agent IDs (empty, special characters)
   - Invalid wildcards (multiple, in middle, in server names)
   - Invalid field types (servers, tools, defaults)

3. `TestReloadConfigs` (9 tests)
   - Valid reload
   - File not found (both MCP and rules)
   - Invalid JSON (both MCP and rules)
   - Invalid structure (both MCP and rules)
   - Undefined servers in rules
   - Path expansion

4. `TestGetStoredConfigPaths` (3 tests)
   - Initially None
   - Stored after loading MCP config
   - Stored after loading gateway rules

### Running Tests

```bash
# All config tests
uv run pytest tests/test_config.py tests/test_validation_and_reload.py -v

# Just new validation tests
uv run pytest tests/test_validation_and_reload.py -v

# All tests (including integration)
uv run pytest tests/ -v
```

### Demo Script

A demo script is provided at `tests/demo_validation.py` that demonstrates:
1. Validation functions with valid and invalid configs
2. Reload functionality with various error scenarios
3. Edge cases (empty configs, wildcards, hierarchical agents)

Run with:
```bash
uv run python -c "import sys; sys.path.insert(0, '.'); from tests.demo_validation import *; demo_validation(); demo_reload(); demo_edge_cases()"
```

## Backward Compatibility

**No Breaking Changes:**
- All existing functionality preserved
- Existing `load_mcp_config()` and `load_gateway_rules()` work exactly as before
- Only additions: new validation functions and path storage
- All 43 existing tests pass unchanged

**New Features:**
- Validation can now be performed without loading from files
- Config paths are stored for future reload operations
- `reload_configs()` provides one-step validation of both configs

## Implementation Quality

### Type Hints
All new functions have complete type hints:
```python
def validate_mcp_config(config: dict) -> tuple[bool, Optional[str]]: ...
def validate_gateway_rules(rules: dict) -> tuple[bool, Optional[str]]: ...
def reload_configs(mcp_config_path: str, gateway_rules_path: str)
    -> tuple[Optional[dict], Optional[dict], Optional[str]]: ...
def get_stored_config_paths() -> tuple[Optional[str], Optional[str]]: ...
```

### Docstrings
All new functions have comprehensive docstrings with:
- Purpose description
- Args documentation
- Returns documentation
- Usage examples where appropriate

### Error Messages
Error messages are:
- Descriptive (identify exact problem)
- Contextual (include agent ID, server name, field path)
- Actionable (tell user what to fix)

**Examples:**
- `'Server "test" must specify either "command" (stdio) or "url" (HTTP) transport'`
- `'Agent "test" allow.tools["db"][0]: wildcard in pattern "get_*_all" must be at start, end, or alone'`
- `'Gateway rules reference undefined servers:\n  - Agent "backend" allow.servers references undefined server "nonexistent"'`

## Next Steps (Not Implemented)

This implementation covers **Phase 1: Validation Framework** only. Future phases will add:

**Phase 2: File Watching**
- Monitor config files for changes
- Trigger reload on modification
- Debounce rapid changes

**Phase 3: Atomic Application**
- Apply validated configs to running gateway
- Handle downstream server lifecycle
- Maintain active sessions

**Phase 4: Rollback & Monitoring**
- Track config versions
- Rollback on application failure
- Emit reload metrics and events

## Summary

### What Was Added
1. ✅ `validate_mcp_config()` - Validate MCP config structure
2. ✅ `validate_gateway_rules()` - Validate gateway rules structure
3. ✅ `reload_configs()` - Load and validate both configs
4. ✅ `get_stored_config_paths()` - Retrieve stored config paths
5. ✅ Config path storage in `load_mcp_config()` and `load_gateway_rules()`
6. ✅ 53 comprehensive tests
7. ✅ Demo script

### What They Validate
- **MCP Config:** Structure, transport types, field types, URLs, required fields
- **Gateway Rules:** Structure, agent IDs, wildcards, tool patterns, defaults
- **Cross-validation:** Servers referenced in rules exist in config

### How reload_configs() Works
1. Loads MCP config from disk (no env var substitution)
2. Validates MCP config structure
3. Loads gateway rules from disk
4. Validates gateway rules structure
5. Cross-validates server references
6. Returns both configs if valid, error message if not

### Edge Cases Handled
- Empty but valid configs
- Complex wildcard patterns
- Hierarchical agent names
- Path expansion
- JSON syntax errors
- Cross-validation with detailed warnings
- Multiple validation errors reported clearly

### Test Results
- **96 total tests pass** (43 existing + 53 new)
- **100% backward compatibility** - all existing tests pass unchanged
- **Comprehensive coverage** - valid cases, invalid cases, edge cases
- **Clear assertions** - error messages validated for clarity

## Files Modified

1. `src/config.py`
   - Added: 4 new functions
   - Added: 2 global variables
   - Modified: 2 existing functions (added path storage)
   - Lines added: ~330

2. `tests/test_validation_and_reload.py`
   - New file: 53 tests
   - Lines: ~700

3. `tests/demo_validation.py`
   - New file: Demonstration script
   - Lines: ~200
