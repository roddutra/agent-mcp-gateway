"""Demo script to show validation and reload functionality."""

import json
import tempfile
from pathlib import Path
from src.config import validate_mcp_config, validate_gateway_rules, reload_configs


def demo_validation():
    """Demonstrate validation functions."""
    print("=" * 70)
    print("VALIDATION FRAMEWORK DEMO")
    print("=" * 70)

    # Test 1: Valid MCP config
    print("\n1. Validating a VALID MCP config:")
    valid_mcp = {
        "mcpServers": {
            "brave-search": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"]
            }
        }
    }
    valid, error = validate_mcp_config(valid_mcp)
    print(f"   Result: valid={valid}, error={error}")

    # Test 2: Invalid MCP config
    print("\n2. Validating an INVALID MCP config (missing mcpServers key):")
    invalid_mcp = {"wrong_key": {}}
    valid, error = validate_mcp_config(invalid_mcp)
    print(f"   Result: valid={valid}")
    print(f"   Error: {error}")

    # Test 3: Valid gateway rules
    print("\n3. Validating VALID gateway rules:")
    valid_rules = {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search"],
                    "tools": {"brave-search": ["*"]}
                }
            }
        }
    }
    valid, error = validate_gateway_rules(valid_rules)
    print(f"   Result: valid={valid}, error={error}")

    # Test 4: Invalid gateway rules
    print("\n4. Validating INVALID gateway rules (invalid wildcard pattern):")
    invalid_rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["db"],
                    "tools": {"db": ["get_*_all"]}  # Multiple wildcards not allowed
                }
            }
        }
    }
    valid, error = validate_gateway_rules(invalid_rules)
    print(f"   Result: valid={valid}")
    print(f"   Error: {error}")


def demo_reload():
    """Demonstrate reload_configs function."""
    print("\n" + "=" * 70)
    print("RELOAD FUNCTIONALITY DEMO")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Test 1: Reload valid configs
        print("\n1. Reloading VALID configurations:")
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "postgres": {"command": "uvx", "args": ["mcp-server-postgres"]}
            }
        }, indent=2))

        rules_file.write_text(json.dumps({
            "agents": {
                "backend": {
                    "allow": {
                        "servers": ["postgres"],
                        "tools": {"postgres": ["query", "list_*"]}
                    }
                }
            }
        }, indent=2))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )
        print(f"   Result: error={error}")
        print(f"   MCP servers loaded: {list(mcp_config['mcpServers'].keys()) if mcp_config else None}")
        print(f"   Agents loaded: {list(gateway_rules['agents'].keys()) if gateway_rules else None}")

        # Test 2: Reload with validation error
        print("\n2. Reloading with VALIDATION ERROR (undefined server in rules):")
        rules_file.write_text(json.dumps({
            "agents": {
                "backend": {
                    "allow": {
                        "servers": ["postgres", "nonexistent"],  # nonexistent server
                        "tools": {"postgres": ["query"]}
                    }
                }
            }
        }, indent=2))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )
        print(f"   Result: Configs loaded={mcp_config is not None}")
        print(f"   Error message:\n{error}")

        # Test 3: Reload with JSON syntax error
        print("\n3. Reloading with JSON SYNTAX ERROR:")
        mcp_file.write_text("{ invalid json }")

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )
        print(f"   Result: Configs loaded={mcp_config is not None}")
        print(f"   Error message: {error}")


def demo_edge_cases():
    """Demonstrate edge case handling."""
    print("\n" + "=" * 70)
    print("EDGE CASES DEMO")
    print("=" * 70)

    # Test 1: Empty but valid configs
    print("\n1. Empty but VALID configurations:")
    empty_mcp = {"mcpServers": {}}
    empty_rules = {"agents": {}}

    valid1, error1 = validate_mcp_config(empty_mcp)
    valid2, error2 = validate_gateway_rules(empty_rules)
    print(f"   Empty MCP config: valid={valid1}, error={error1}")
    print(f"   Empty gateway rules: valid={valid2}, error={error2}")

    # Test 2: Complex wildcard patterns
    print("\n2. Complex wildcard patterns:")
    complex_rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["db"],
                    "tools": {
                        "db": ["*", "get_*", "*_query", "list_*"]
                    }
                }
            }
        }
    }
    valid, error = validate_gateway_rules(complex_rules)
    print(f"   Multiple wildcard patterns: valid={valid}, error={error}")

    # Test 3: Hierarchical agent names
    print("\n3. Hierarchical agent names:")
    hierarchical_rules = {
        "agents": {
            "team.backend": {"allow": {"servers": ["db"]}},
            "team.frontend": {"allow": {"servers": ["api"]}},
            "org_admin": {"allow": {"servers": ["*"]}}
        }
    }
    valid, error = validate_gateway_rules(hierarchical_rules)
    print(f"   Hierarchical agents: valid={valid}, error={error}")
    print(f"   Agent IDs: {list(hierarchical_rules['agents'].keys())}")


if __name__ == "__main__":
    demo_validation()
    demo_reload()
    demo_edge_cases()

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
