"""Test configuration module with simple inline tests."""

import json
import os
import tempfile
from pathlib import Path

from src.config import (
    load_mcp_config,
    load_gateway_rules,
    validate_rules_against_servers,
    get_config_path,
)


def test_valid_mcp_config():
    """Test loading a valid MCP server configuration."""
    config = {
        "mcpServers": {
            "brave-search": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                "env": {"BRAVE_API_KEY": "test_key"}
            },
            "postgres": {
                "command": "uvx",
                "args": ["mcp-server-postgres"]
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        temp_path = f.name

    try:
        loaded = load_mcp_config(temp_path)
        assert "mcpServers" in loaded
        assert "brave-search" in loaded["mcpServers"]
        assert "postgres" in loaded["mcpServers"]
        print("✓ Valid MCP config test passed")
    finally:
        os.unlink(temp_path)


def test_env_var_substitution():
    """Test environment variable substitution."""
    os.environ["TEST_API_KEY"] = "secret_value"

    config = {
        "mcpServers": {
            "test-server": {
                "command": "npx",
                "args": ["test"],
                "env": {"API_KEY": "${TEST_API_KEY}"}
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        temp_path = f.name

    try:
        loaded = load_mcp_config(temp_path)
        assert loaded["mcpServers"]["test-server"]["env"]["API_KEY"] == "secret_value"
        print("✓ Environment variable substitution test passed")
    finally:
        os.unlink(temp_path)
        del os.environ["TEST_API_KEY"]


def test_missing_env_var():
    """Test error handling for missing environment variables."""
    config = {
        "mcpServers": {
            "test-server": {
                "command": "npx",
                "args": ["test"],
                "env": {"API_KEY": "${MISSING_VAR}"}
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        temp_path = f.name

    try:
        load_mcp_config(temp_path)
        assert False, "Should have raised ValueError for missing env var"
    except ValueError as e:
        assert "MISSING_VAR" in str(e)
        print("✓ Missing environment variable error test passed")
    finally:
        os.unlink(temp_path)


def test_http_transport():
    """Test HTTP transport configuration."""
    config = {
        "mcpServers": {
            "http-server": {
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer token"}
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        temp_path = f.name

    try:
        loaded = load_mcp_config(temp_path)
        assert loaded["mcpServers"]["http-server"]["url"] == "https://example.com/mcp"
        print("✓ HTTP transport test passed")
    finally:
        os.unlink(temp_path)


def test_invalid_transport():
    """Test error for missing transport specification."""
    config = {
        "mcpServers": {
            "invalid-server": {
                "name": "test"
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        temp_path = f.name

    try:
        load_mcp_config(temp_path)
        assert False, "Should have raised ValueError for missing transport"
    except ValueError as e:
        assert "command" in str(e) or "url" in str(e)
        print("✓ Invalid transport error test passed")
    finally:
        os.unlink(temp_path)


def test_valid_gateway_rules():
    """Test loading valid gateway rules."""
    rules = {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search"],
                    "tools": {"brave-search": ["*"]}
                }
            },
            "backend": {
                "allow": {
                    "servers": ["postgres"],
                    "tools": {"postgres": ["query", "list_*"]}
                },
                "deny": {
                    "tools": {"postgres": ["drop_*"]}
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": True
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(rules, f)
        temp_path = f.name

    try:
        loaded = load_gateway_rules(temp_path)
        assert "agents" in loaded
        assert "researcher" in loaded["agents"]
        assert "backend" in loaded["agents"]
        print("✓ Valid gateway rules test passed")
    finally:
        os.unlink(temp_path)


def test_hierarchical_agent_names():
    """Test support for hierarchical agent names (team.role)."""
    rules = {
        "agents": {
            "team.researcher": {
                "allow": {
                    "servers": ["brave-search"]
                }
            },
            "company.team.developer": {
                "allow": {
                    "servers": ["postgres"]
                }
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(rules, f)
        temp_path = f.name

    try:
        loaded = load_gateway_rules(temp_path)
        assert "team.researcher" in loaded["agents"]
        assert "company.team.developer" in loaded["agents"]
        print("✓ Hierarchical agent names test passed")
    finally:
        os.unlink(temp_path)


def test_wildcard_validation():
    """Test wildcard pattern validation."""
    # Valid wildcards
    valid_rules = {
        "agents": {
            "test": {
                "allow": {
                    "tools": {
                        "server": ["*", "get_*", "*_query"]
                    }
                }
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(valid_rules, f)
        temp_path = f.name

    try:
        loaded = load_gateway_rules(temp_path)
        print("✓ Valid wildcard patterns test passed")
    finally:
        os.unlink(temp_path)

    # Invalid wildcard (multiple)
    invalid_rules = {
        "agents": {
            "test": {
                "allow": {
                    "tools": {
                        "server": ["get_*_all"]
                    }
                }
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(invalid_rules, f)
        temp_path = f.name

    try:
        load_gateway_rules(temp_path)
        assert False, "Should have raised ValueError for wildcard in middle"
    except ValueError as e:
        assert "must be at start, end, or alone" in str(e)
        print("✓ Invalid wildcard patterns error test passed")
    finally:
        os.unlink(temp_path)


def test_validate_rules_against_servers():
    """Test cross-validation of rules against server config."""
    mcp_config = {
        "mcpServers": {
            "brave-search": {"command": "npx"},
            "postgres": {"command": "uvx"}
        }
    }

    rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["brave-search", "nonexistent"],
                    "tools": {"missing-server": ["*"]}
                }
            }
        }
    }

    warnings = validate_rules_against_servers(rules, mcp_config)
    assert len(warnings) == 2
    assert any("nonexistent" in w for w in warnings)
    assert any("missing-server" in w for w in warnings)
    print("✓ Cross-validation test passed")


def test_get_config_path():
    """Test config path resolution."""
    # Test default
    path = get_config_path("NONEXISTENT_VAR", "./default.json")
    assert "default.json" in path

    # Test environment variable
    os.environ["TEST_CONFIG_PATH"] = "~/test.json"
    path = get_config_path("TEST_CONFIG_PATH", "./default.json")
    assert "test.json" in path
    assert "~" not in path  # Should be expanded
    del os.environ["TEST_CONFIG_PATH"]

    print("✓ Config path resolution test passed")


def test_file_not_found():
    """Test error handling for missing files."""
    try:
        load_mcp_config("/nonexistent/path/config.json")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "not found" in str(e).lower()
        print("✓ File not found error test passed")


def test_invalid_json():
    """Test error handling for invalid JSON."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{invalid json content")
        temp_path = f.name

    try:
        load_mcp_config(temp_path)
        assert False, "Should have raised JSONDecodeError"
    except json.JSONDecodeError as e:
        assert "Invalid JSON" in str(e)
        print("✓ Invalid JSON error test passed")
    finally:
        os.unlink(temp_path)


if __name__ == "__main__":
    print("Running configuration module tests...\n")

    test_valid_mcp_config()
    test_env_var_substitution()
    test_missing_env_var()
    test_http_transport()
    test_invalid_transport()
    test_valid_gateway_rules()
    test_hierarchical_agent_names()
    test_wildcard_validation()
    test_validate_rules_against_servers()
    test_get_config_path()
    test_file_not_found()
    test_invalid_json()

    print("\n✓ All tests passed!")
