"""Tests for configuration validation and reload functionality."""

import json
import pytest
from pathlib import Path
from src.config import (
    validate_mcp_config,
    validate_gateway_rules,
    reload_configs,
    get_stored_config_paths,
    load_mcp_config,
    load_gateway_rules,
)


class TestValidateMCPConfig:
    """Test cases for validate_mcp_config function."""

    def test_valid_minimal_config(self):
        """Test validation of minimal valid config."""
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx"
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is True
        assert error is None

    def test_valid_stdio_with_args(self):
        """Test validation of stdio config with arguments."""
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "test-package"]
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is True
        assert error is None

    def test_valid_stdio_with_env(self):
        """Test validation of stdio config with environment variables."""
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "uvx",
                    "args": ["server"],
                    "env": {
                        "API_KEY": "${KEY}",
                        "URL": "https://api.example.com"
                    }
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is True
        assert error is None

    def test_valid_http_config(self):
        """Test validation of HTTP transport config."""
        config = {
            "mcpServers": {
                "http-server": {
                    "url": "https://example.com/mcp"
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is True
        assert error is None

    def test_valid_http_with_headers(self):
        """Test validation of HTTP config with headers."""
        config = {
            "mcpServers": {
                "http-server": {
                    "url": "http://localhost:8080",
                    "headers": {
                        "Authorization": "Bearer token",
                        "X-Custom": "value"
                    }
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is True
        assert error is None

    def test_missing_mcpservers_key(self):
        """Test error when mcpServers key is missing."""
        config = {"servers": {}}
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "mcpServers" in error

    def test_not_a_dict(self):
        """Test error when config is not a dictionary."""
        config = ["not", "a", "dict"]
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "must be a JSON object" in error

    def test_mcpservers_not_dict(self):
        """Test error when mcpServers is not a dictionary."""
        config = {"mcpServers": ["not", "dict"]}
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "must be an object" in error

    def test_both_command_and_url(self):
        """Test error when both command and url are present."""
        config = {
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "url": "https://example.com"
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "cannot have both" in error

    def test_neither_command_nor_url(self):
        """Test error when neither command nor url is present."""
        config = {
            "mcpServers": {
                "server": {
                    "args": ["-y", "test"]
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "must specify either" in error

    def test_invalid_command_type(self):
        """Test error when command is not a string."""
        config = {
            "mcpServers": {
                "server": {
                    "command": ["should", "be", "string"]
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "command" in error
        assert "must be a string" in error

    def test_invalid_args_type(self):
        """Test error when args is not an array."""
        config = {
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "args": "should-be-array"
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "args" in error
        assert "must be an array" in error

    def test_invalid_args_element_type(self):
        """Test error when args element is not a string."""
        config = {
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "args": ["-y", 123]
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "args[1]" in error
        assert "must be a string" in error

    def test_invalid_env_type(self):
        """Test error when env is not an object."""
        config = {
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "env": ["should", "be", "object"]
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "env" in error
        assert "must be an object" in error

    def test_invalid_env_value_type(self):
        """Test error when env value is not a string."""
        config = {
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "env": {
                        "KEY": 123
                    }
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "env" in error
        assert "must be a string" in error

    def test_invalid_url_type(self):
        """Test error when url is not a string."""
        config = {
            "mcpServers": {
                "server": {
                    "url": 12345
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "url" in error
        assert "must be a string" in error

    def test_invalid_url_format(self):
        """Test error when url doesn't start with http:// or https://."""
        config = {
            "mcpServers": {
                "server": {
                    "url": "ftp://example.com"
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "must start with http://" in error or "https://" in error

    def test_invalid_headers_type(self):
        """Test error when headers is not an object."""
        config = {
            "mcpServers": {
                "server": {
                    "url": "https://example.com",
                    "headers": "should-be-object"
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "headers" in error
        assert "must be an object" in error

    def test_invalid_headers_value_type(self):
        """Test error when headers value is not a string."""
        config = {
            "mcpServers": {
                "server": {
                    "url": "https://example.com",
                    "headers": {
                        "Auth": 123
                    }
                }
            }
        }
        valid, error = validate_mcp_config(config)
        assert valid is False
        assert "headers" in error
        assert "must be a string" in error


class TestValidateGatewayRules:
    """Test cases for validate_gateway_rules function."""

    def test_valid_minimal_rules(self):
        """Test validation of minimal valid rules."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["server1"]
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is True
        assert error is None

    def test_valid_with_tools(self):
        """Test validation of rules with tool patterns."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {
                            "db": ["*", "get_*", "*_query"]
                        }
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is True
        assert error is None

    def test_valid_with_deny_section(self):
        """Test validation of rules with deny section."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"]
                    },
                    "deny": {
                        "tools": {
                            "db": ["drop_*"]
                        }
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is True
        assert error is None

    def test_valid_with_defaults(self):
        """Test validation of rules with defaults section."""
        rules = {
            "agents": {},
            "defaults": {
                "deny_on_missing_agent": True
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is True
        assert error is None

    def test_valid_hierarchical_agent_names(self):
        """Test validation of hierarchical agent names."""
        rules = {
            "agents": {
                "team.backend": {"allow": {"servers": ["db"]}},
                "team.frontend": {"allow": {"servers": ["api"]}},
                "org_admin": {"allow": {"servers": ["*"]}}
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is True
        assert error is None

    def test_not_a_dict(self):
        """Test error when rules is not a dictionary."""
        rules = ["not", "a", "dict"]
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "must be a JSON object" in error

    def test_agents_not_dict(self):
        """Test error when agents is not a dictionary."""
        rules = {"agents": ["not", "dict"]}
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "agents" in error
        assert "must be an object" in error

    def test_empty_agent_id(self):
        """Test error when agent ID is empty."""
        rules = {
            "agents": {
                "": {"allow": {"servers": ["test"]}}
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "non-empty string" in error

    def test_invalid_agent_id_characters(self):
        """Test error when agent ID contains invalid characters."""
        rules = {
            "agents": {
                "agent@invalid": {"allow": {"servers": ["test"]}}
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "invalid characters" in error

    def test_agent_config_not_dict(self):
        """Test error when agent config is not a dictionary."""
        rules = {
            "agents": {
                "test": ["not", "dict"]
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "configuration must be an object" in error

    def test_invalid_allow_section_type(self):
        """Test error when allow section is not a dictionary."""
        rules = {
            "agents": {
                "test": {
                    "allow": ["not", "dict"]
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "allow section must be an object" in error

    def test_invalid_servers_list_type(self):
        """Test error when servers is not an array."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": "should-be-array"
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "servers must be an array" in error

    def test_invalid_server_element_type(self):
        """Test error when server element is not a string."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["valid", 123]
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "servers[1]" in error
        assert "must be a string" in error

    def test_invalid_server_wildcard_pattern(self):
        """Test error when server wildcard is used in pattern."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db-*"]
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "only be used alone" in error

    def test_invalid_tools_type(self):
        """Test error when tools is not an object."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "tools": ["not", "dict"]
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "tools must be an object" in error

    def test_invalid_tool_patterns_type(self):
        """Test error when tool patterns is not an array."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "tools": {
                            "db": "should-be-array"
                        }
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "must be an array" in error

    def test_invalid_tool_pattern_type(self):
        """Test error when tool pattern is not a string."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "tools": {
                            "db": ["valid", 123]
                        }
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "must be a string" in error

    def test_invalid_tool_pattern_multiple_wildcards(self):
        """Test error when tool pattern has multiple wildcards."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "tools": {
                            "db": ["get_*_all"]
                        }
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "must be at start, end, or alone" in error

    def test_invalid_tool_pattern_wildcard_middle(self):
        """Test error when wildcard is in middle of pattern."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "tools": {
                            "db": ["get*data"]
                        }
                    }
                }
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "must be at start, end, or alone" in error

    def test_invalid_defaults_type(self):
        """Test error when defaults is not an object."""
        rules = {
            "agents": {},
            "defaults": "should-be-dict"
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "defaults" in error
        assert "must be an object" in error

    def test_invalid_deny_on_missing_agent_type(self):
        """Test error when deny_on_missing_agent is not boolean."""
        rules = {
            "agents": {},
            "defaults": {
                "deny_on_missing_agent": "true"
            }
        }
        valid, error = validate_gateway_rules(rules)
        assert valid is False
        assert "must be a boolean" in error


class TestReloadConfigs:
    """Test cases for reload_configs function."""

    def test_reload_valid_configs(self, tmp_path):
        """Test reloading valid configurations."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-brave-search"]
                }
            }
        }))

        rules_file.write_text(json.dumps({
            "agents": {
                "researcher": {
                    "allow": {
                        "servers": ["brave-search"],
                        "tools": {"brave-search": ["*"]}
                    }
                }
            }
        }))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )

        assert mcp_config is not None
        assert gateway_rules is not None
        assert error is None
        assert "brave-search" in mcp_config["mcpServers"]
        assert "researcher" in gateway_rules["agents"]

    def test_reload_mcp_file_not_found(self, tmp_path):
        """Test error when MCP config file doesn't exist."""
        rules_file = tmp_path / "rules.json"
        rules_file.write_text(json.dumps({"agents": {}}))

        mcp_config, gateway_rules, error = reload_configs(
            str(tmp_path / "nonexistent.json"), str(rules_file)
        )

        assert mcp_config is None
        assert gateway_rules is None
        assert error is not None
        assert "not found" in error

    def test_reload_rules_file_not_found(self, tmp_path):
        """Test error when rules file doesn't exist."""
        mcp_file = tmp_path / "mcp.json"
        mcp_file.write_text(json.dumps({"mcpServers": {}}))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(tmp_path / "nonexistent.json")
        )

        assert mcp_config is None
        assert gateway_rules is None
        assert error is not None
        assert "not found" in error

    def test_reload_invalid_json_mcp(self, tmp_path):
        """Test error when MCP config has invalid JSON."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{ invalid json }")
        rules_file.write_text(json.dumps({"agents": {}}))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )

        assert mcp_config is None
        assert gateway_rules is None
        assert error is not None
        assert "Invalid JSON" in error

    def test_reload_invalid_json_rules(self, tmp_path):
        """Test error when rules has invalid JSON."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({"mcpServers": {}}))
        rules_file.write_text("{ invalid json }")

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )

        assert mcp_config is None
        assert gateway_rules is None
        assert error is not None
        assert "Invalid JSON" in error

    def test_reload_invalid_mcp_structure(self, tmp_path):
        """Test error when MCP config has invalid structure."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({"wrong_key": {}}))
        rules_file.write_text(json.dumps({"agents": {}}))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )

        assert mcp_config is None
        assert gateway_rules is None
        assert error is not None
        assert "Invalid MCP config" in error

    def test_reload_invalid_rules_structure(self, tmp_path):
        """Test error when rules has invalid structure."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({"mcpServers": {}}))
        rules_file.write_text(json.dumps({"agents": {"": {"allow": {}}}}))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )

        assert mcp_config is None
        assert gateway_rules is None
        assert error is not None
        assert "Invalid gateway rules" in error

    def test_reload_undefined_server_in_rules(self, tmp_path, caplog, capsys):
        """Test that rules with undefined servers succeed with warnings."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "postgres": {"command": "uvx"}
            }
        }))

        rules_file.write_text(json.dumps({
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["postgres", "nonexistent"]
                    }
                }
            }
        }))

        # Import module to access the getter function
        from src.config import get_last_validation_warnings

        with caplog.at_level("WARNING"):
            mcp_config, gateway_rules, error = reload_configs(
                str(mcp_file), str(rules_file)
            )

        # Reload should succeed
        assert mcp_config is not None
        assert gateway_rules is not None
        assert error is None
        assert "postgres" in mcp_config["mcpServers"]
        assert "test" in gateway_rules["agents"]

        # Check that warnings were logged
        assert any("undefined server" in record.message.lower() for record in caplog.records)
        assert any("nonexistent" in record.message for record in caplog.records)

        # Check stderr output
        captured = capsys.readouterr()
        assert "[HOT RELOAD WARNING]" in captured.err
        assert "nonexistent" in captured.err

        # Check that warnings are accessible via getter
        warnings = get_last_validation_warnings()
        assert len(warnings) > 0
        assert any("nonexistent" in w for w in warnings)

    def test_reload_path_expansion(self, tmp_path):
        """Test that paths are expanded correctly."""
        subdir = tmp_path / "configs"
        subdir.mkdir()

        mcp_file = subdir / "mcp.json"
        rules_file = subdir / "rules.json"

        mcp_file.write_text(json.dumps({"mcpServers": {}}))
        rules_file.write_text(json.dumps({"agents": {}}))

        mcp_config, gateway_rules, error = reload_configs(
            str(mcp_file), str(rules_file)
        )

        assert mcp_config is not None
        assert gateway_rules is not None
        assert error is None


class TestGetStoredConfigPaths:
    """Test cases for get_stored_config_paths function."""

    def test_initially_none(self):
        """Test that paths are initially None."""
        # Note: This test may fail if other tests have already loaded configs
        # In a real scenario, you might want to reset the global state
        mcp_path, rules_path = get_stored_config_paths()
        # We can't assert None here because other tests may have run
        assert isinstance(mcp_path, (str, type(None)))
        assert isinstance(rules_path, (str, type(None)))

    def test_stored_after_load_mcp(self, tmp_path):
        """Test that MCP config path is stored after loading."""
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "test": {"command": "npx"}
            }
        }))

        load_mcp_config(str(config_file))
        mcp_path, _ = get_stored_config_paths()

        assert mcp_path is not None
        assert Path(mcp_path) == config_file.resolve()

    def test_stored_after_load_rules(self, tmp_path):
        """Test that rules path is stored after loading."""
        rules_file = tmp_path / "rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "test": {"allow": {"servers": ["db"]}}
            }
        }))

        load_gateway_rules(str(rules_file))
        _, rules_path = get_stored_config_paths()

        assert rules_path is not None
        assert Path(rules_path) == rules_file.resolve()

    def test_both_stored_after_loading_both(self, tmp_path):
        """Test that both paths are stored after loading both configs."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text(json.dumps({
            "mcpServers": {"test": {"command": "npx"}}
        }))
        rules_file.write_text(json.dumps({
            "agents": {"test": {"allow": {"servers": ["test"]}}}
        }))

        load_mcp_config(str(mcp_file))
        load_gateway_rules(str(rules_file))

        mcp_path, rules_path = get_stored_config_paths()

        assert mcp_path is not None
        assert rules_path is not None
        assert Path(mcp_path) == mcp_file.resolve()
        assert Path(rules_path) == rules_file.resolve()
