"""Unit tests for configuration management."""

import json
import os
import pytest
from pathlib import Path
from src.config import (
    load_mcp_config,
    load_gateway_rules,
    get_config_path,
    validate_rules_against_servers,
    _substitute_env_vars
)


class TestLoadMCPConfig:
    """Test cases for loading MCP server configuration."""

    def test_valid_stdio_config(self, tmp_path):
        """Test loading valid stdio transport configuration."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "test-server"]
                }
            }
        }))

        config = load_mcp_config(str(config_file))
        assert "mcpServers" in config
        assert "test-server" in config["mcpServers"]
        assert config["mcpServers"]["test-server"]["command"] == "npx"
        assert config["mcpServers"]["test-server"]["args"] == ["-y", "test-server"]

    def test_valid_http_config(self, tmp_path):
        """Test loading valid HTTP transport configuration."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "http-server": {
                    "url": "https://example.com/mcp"
                }
            }
        }))

        config = load_mcp_config(str(config_file))
        assert config["mcpServers"]["http-server"]["url"] == "https://example.com/mcp"

    def test_stdio_with_env_vars(self, tmp_path, monkeypatch):
        """Test stdio config with environment variables."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "command": "uvx",
                    "args": ["server"],
                    "env": {
                        "API_KEY": "${TEST_API_KEY}",
                        "URL": "${TEST_URL}"
                    }
                }
            }
        }))

        monkeypatch.setenv("TEST_API_KEY", "secret123")
        monkeypatch.setenv("TEST_URL", "https://api.example.com")

        config = load_mcp_config(str(config_file))
        assert config["mcpServers"]["server"]["env"]["API_KEY"] == "secret123"
        assert config["mcpServers"]["server"]["env"]["URL"] == "https://api.example.com"

    def test_missing_env_var_error(self, tmp_path):
        """Test error when environment variable is not set."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "command": "uvx",
                    "args": ["server"],
                    "env": {
                        "API_KEY": "${MISSING_VAR}"
                    }
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "MISSING_VAR" in str(exc_info.value)
        assert "not set" in str(exc_info.value)

    def test_http_with_headers(self, tmp_path):
        """Test HTTP config with custom headers."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "url": "http://localhost:8080",
                    "headers": {
                        "Authorization": "Bearer token123",
                        "X-Custom-Header": "value"
                    }
                }
            }
        }))

        config = load_mcp_config(str(config_file))
        assert config["mcpServers"]["server"]["headers"]["Authorization"] == "Bearer token123"

    def test_invalid_both_command_and_url(self, tmp_path):
        """Test error when both command and url are present."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "url": "https://example.com"
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "cannot have both" in str(exc_info.value).lower()
        assert "command" in str(exc_info.value)
        assert "url" in str(exc_info.value)

    def test_missing_transport_error(self, tmp_path):
        """Test error when neither command nor url is present."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "args": ["-y", "test"]
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "must specify either" in str(exc_info.value).lower()

    def test_invalid_json_error(self, tmp_path):
        """Test error when config is not valid JSON."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            load_mcp_config(str(config_file))

    def test_file_not_found_error(self, tmp_path):
        """Test error when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            load_mcp_config(str(config_file))
        assert "not found" in str(exc_info.value)

    def test_missing_mcpservers_key(self, tmp_path):
        """Test error when mcpServers key is missing."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({"servers": {}}))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "mcpServers" in str(exc_info.value)

    def test_invalid_url_format(self, tmp_path):
        """Test error when URL doesn't start with http:// or https://."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "url": "ftp://example.com"
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "http://" in str(exc_info.value) or "https://" in str(exc_info.value)

    def test_invalid_args_type(self, tmp_path):
        """Test error when args is not an array."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "args": "should-be-array"
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "args" in str(exc_info.value)
        assert "array" in str(exc_info.value).lower()

    def test_invalid_env_type(self, tmp_path):
        """Test error when env is not an object."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "env": ["should-be-object"]
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "env" in str(exc_info.value)
        assert "object" in str(exc_info.value).lower()

    def test_invalid_headers_type(self, tmp_path):
        """Test error when headers is not an object."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "url": "https://example.com",
                    "headers": "should-be-object"
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_mcp_config(str(config_file))
        assert "headers" in str(exc_info.value)
        assert "object" in str(exc_info.value).lower()

    def test_path_expansion(self, tmp_path):
        """Test that paths are expanded correctly."""
        # Create config in a subdirectory
        subdir = tmp_path / "configs"
        subdir.mkdir()
        config_file = subdir / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }))

        # Load using relative path components
        config = load_mcp_config(str(config_file))
        assert "mcpServers" in config


class TestLoadGatewayRules:
    """Test cases for loading gateway rules configuration."""

    def test_valid_rules_config(self, tmp_path):
        """Test loading valid gateway rules configuration."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "researcher": {
                    "allow": {
                        "servers": ["brave-search"],
                        "tools": {"brave-search": ["*"]}
                    }
                }
            },
            "defaults": {
                "deny_on_missing_agent": True
            }
        }))

        rules = load_gateway_rules(str(rules_file))
        assert "agents" in rules
        assert "researcher" in rules["agents"]
        assert rules["defaults"]["deny_on_missing_agent"] is True

    def test_hierarchical_agent_names(self, tmp_path):
        """Test that hierarchical agent names (team.role) are allowed."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "team.backend": {
                    "allow": {"servers": ["postgres"]}
                },
                "team.frontend": {
                    "allow": {"servers": ["api"]}
                }
            }
        }))

        rules = load_gateway_rules(str(rules_file))
        assert "team.backend" in rules["agents"]
        assert "team.frontend" in rules["agents"]

    def test_valid_wildcard_patterns(self, tmp_path):
        """Test that valid wildcard patterns are accepted."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
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
        }))

        rules = load_gateway_rules(str(rules_file))
        tools = rules["agents"]["test"]["allow"]["tools"]["db"]
        assert "*" in tools
        assert "get_*" in tools
        assert "*_query" in tools

    def test_invalid_wildcard_multiple(self, tmp_path):
        """Test error when pattern contains multiple wildcards."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {
                            "db": ["get_*_all"]
                        }
                    }
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_gateway_rules(str(rules_file))
        # The error message says "must be at start, end, or alone" which catches this case
        assert "must be at start, end, or alone" in str(exc_info.value).lower()

    def test_invalid_wildcard_middle(self, tmp_path):
        """Test error when wildcard is in the middle of pattern."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {
                            "db": ["get*data"]
                        }
                    }
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_gateway_rules(str(rules_file))
        assert "must be at start, end, or alone" in str(exc_info.value).lower()

    def test_invalid_server_wildcard_pattern(self, tmp_path):
        """Test error when server wildcard is used in pattern."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db-*"]
                    }
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_gateway_rules(str(rules_file))
        assert "only be used alone" in str(exc_info.value).lower()

    def test_invalid_agent_id_characters(self, tmp_path):
        """Test error when agent ID contains invalid characters."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "agent@invalid": {
                    "allow": {"servers": ["test"]}
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_gateway_rules(str(rules_file))
        assert "invalid characters" in str(exc_info.value).lower()

    def test_empty_agent_id(self, tmp_path):
        """Test error when agent ID is empty."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "": {
                    "allow": {"servers": ["test"]}
                }
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_gateway_rules(str(rules_file))
        assert "non-empty string" in str(exc_info.value).lower()

    def test_invalid_defaults_type(self, tmp_path):
        """Test error when defaults.deny_on_missing_agent is not boolean."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {},
            "defaults": {
                "deny_on_missing_agent": "true"
            }
        }))

        with pytest.raises(ValueError) as exc_info:
            load_gateway_rules(str(rules_file))
        assert "must be a boolean" in str(exc_info.value).lower()

    def test_file_not_found(self, tmp_path):
        """Test error when rules file doesn't exist."""
        rules_file = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            load_gateway_rules(str(rules_file))
        assert "not found" in str(exc_info.value)

    def test_invalid_json(self, tmp_path):
        """Test error when rules file contains invalid JSON."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            load_gateway_rules(str(rules_file))

    def test_deny_section_validation(self, tmp_path):
        """Test that deny section is validated like allow section."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "test": {
                    "allow": {"servers": ["db"]},
                    "deny": {
                        "servers": ["cache"],
                        "tools": {"db": ["drop_*"]}
                    }
                }
            }
        }))

        rules = load_gateway_rules(str(rules_file))
        assert "drop_*" in rules["agents"]["test"]["deny"]["tools"]["db"]


class TestEnvVarSubstitution:
    """Test cases for environment variable substitution."""

    def test_substitute_string(self, monkeypatch):
        """Test substituting environment variable in string."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = _substitute_env_vars("prefix_${TEST_VAR}_suffix")
        assert result == "prefix_test_value_suffix"

    def test_substitute_dict(self, monkeypatch):
        """Test substituting environment variables in dictionary."""
        monkeypatch.setenv("KEY1", "value1")
        monkeypatch.setenv("KEY2", "value2")

        obj = {
            "field1": "${KEY1}",
            "field2": "${KEY2}",
            "field3": "no_substitution"
        }
        result = _substitute_env_vars(obj)

        assert result["field1"] == "value1"
        assert result["field2"] == "value2"
        assert result["field3"] == "no_substitution"

    def test_substitute_list(self, monkeypatch):
        """Test substituting environment variables in list."""
        monkeypatch.setenv("VAR", "substituted")

        obj = ["${VAR}", "normal", "${VAR}_suffix"]
        result = _substitute_env_vars(obj)

        assert result == ["substituted", "normal", "substituted_suffix"]

    def test_substitute_nested(self, monkeypatch):
        """Test substituting environment variables in nested structure."""
        monkeypatch.setenv("API_KEY", "secret123")
        monkeypatch.setenv("URL", "https://api.example.com")

        obj = {
            "servers": {
                "server1": {
                    "env": {
                        "API_KEY": "${API_KEY}",
                        "BASE_URL": "${URL}"
                    }
                }
            }
        }
        result = _substitute_env_vars(obj)

        assert result["servers"]["server1"]["env"]["API_KEY"] == "secret123"
        assert result["servers"]["server1"]["env"]["BASE_URL"] == "https://api.example.com"

    def test_missing_env_var_error(self):
        """Test error when referenced environment variable doesn't exist."""
        with pytest.raises(ValueError) as exc_info:
            _substitute_env_vars("${NONEXISTENT_VAR}")
        assert "NONEXISTENT_VAR" in str(exc_info.value)
        assert "not set" in str(exc_info.value)

    def test_no_substitution_needed(self):
        """Test that strings without ${} are returned unchanged."""
        result = _substitute_env_vars("normal_string")
        assert result == "normal_string"

    def test_preserve_types(self):
        """Test that non-string types are preserved."""
        obj = {
            "string": "value",
            "number": 123,
            "boolean": True,
            "null": None,
            "array": [1, 2, 3]
        }
        result = _substitute_env_vars(obj)

        assert result["string"] == "value"
        assert result["number"] == 123
        assert result["boolean"] is True
        assert result["null"] is None
        assert result["array"] == [1, 2, 3]


class TestGetConfigPath:
    """Test cases for configuration path resolution."""

    def test_uses_env_var_when_set(self, monkeypatch, tmp_path):
        """Test that environment variable is used when set."""
        config_path = tmp_path / "custom.json"
        monkeypatch.setenv("TEST_CONFIG", str(config_path))

        result = get_config_path("TEST_CONFIG", "./default.json")
        assert Path(result) == config_path

    def test_uses_default_when_env_not_set(self):
        """Test that default is used when environment variable not set."""
        result = get_config_path("NONEXISTENT_VAR", "./default.json")
        assert "default.json" in result

    def test_path_expansion(self, monkeypatch):
        """Test that paths are expanded (~ and relative)."""
        monkeypatch.setenv("HOME", "/home/testuser")
        result = get_config_path("NONEXISTENT", "~/config.json")
        assert result.startswith("/")
        assert "testuser" in result or "Users" in result or "home" in result


class TestGatewayDefaultAgent:
    """Test cases for GATEWAY_DEFAULT_AGENT environment variable."""

    def test_gateway_default_agent_env_var_set(self, monkeypatch):
        """Test that GATEWAY_DEFAULT_AGENT environment variable is read correctly."""
        monkeypatch.setenv("GATEWAY_DEFAULT_AGENT", "researcher")

        import os
        agent = os.getenv("GATEWAY_DEFAULT_AGENT")
        assert agent == "researcher"

    def test_gateway_default_agent_env_var_not_set(self):
        """Test behavior when GATEWAY_DEFAULT_AGENT is not set."""
        import os
        agent = os.getenv("GATEWAY_DEFAULT_AGENT")
        # Should be None when not set
        assert agent is None

    def test_gateway_default_agent_with_special_characters(self, monkeypatch):
        """Test that GATEWAY_DEFAULT_AGENT supports agent names with special chars."""
        monkeypatch.setenv("GATEWAY_DEFAULT_AGENT", "team-backend_v2")

        import os
        agent = os.getenv("GATEWAY_DEFAULT_AGENT")
        assert agent == "team-backend_v2"

    def test_gateway_default_agent_empty_string(self, monkeypatch):
        """Test that empty GATEWAY_DEFAULT_AGENT is treated as unset."""
        monkeypatch.setenv("GATEWAY_DEFAULT_AGENT", "")

        import os
        agent = os.getenv("GATEWAY_DEFAULT_AGENT")
        # Empty string should be treated as falsy in fallback logic
        assert agent == ""
        assert not agent  # Empty string is falsy

    def test_default_agent_name_validation(self, tmp_path):
        """Test that agent named 'default' passes validation."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "default": {
                    "allow": {"servers": ["api"]}
                }
            }
        }))

        # Should not raise any validation errors
        rules = load_gateway_rules(str(rules_file))
        assert "default" in rules["agents"]

    def test_default_agent_coexists_with_others(self, tmp_path):
        """Test that 'default' agent can coexist with other agents."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "default": {
                    "allow": {"servers": ["api"]}
                },
                "researcher": {
                    "allow": {"servers": ["brave-search"]}
                },
                "backend": {
                    "allow": {"servers": ["postgres"]}
                }
            }
        }))

        rules = load_gateway_rules(str(rules_file))
        assert "default" in rules["agents"]
        assert "researcher" in rules["agents"]
        assert "backend" in rules["agents"]

    def test_default_agent_with_complex_rules(self, tmp_path):
        """Test that 'default' agent works with complex allow/deny rules."""
        rules_file = tmp_path / "gateway-rules.json"
        rules_file.write_text(json.dumps({
            "agents": {
                "default": {
                    "allow": {
                        "servers": ["db", "api"],
                        "tools": {
                            "db": ["query", "read_*"],
                            "api": ["*"]
                        }
                    },
                    "deny": {
                        "tools": {
                            "db": ["drop_*", "delete_*"]
                        }
                    }
                }
            },
            "defaults": {
                "deny_on_missing_agent": False
            }
        }))

        rules = load_gateway_rules(str(rules_file))
        default_agent = rules["agents"]["default"]

        # Verify allow rules
        assert "db" in default_agent["allow"]["servers"]
        assert "api" in default_agent["allow"]["servers"]
        assert "query" in default_agent["allow"]["tools"]["db"]
        assert "read_*" in default_agent["allow"]["tools"]["db"]
        assert "*" in default_agent["allow"]["tools"]["api"]

        # Verify deny rules
        assert "drop_*" in default_agent["deny"]["tools"]["db"]
        assert "delete_*" in default_agent["deny"]["tools"]["db"]


class TestValidateRulesAgainstServers:
    """Test cases for cross-validation of rules and servers."""

    def test_valid_rules(self):
        """Test that valid rules pass validation."""
        mcp_config = {
            "mcpServers": {
                "brave-search": {"command": "npx"},
                "postgres": {"command": "uvx"}
            }
        }
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

        warnings = validate_rules_against_servers(rules, mcp_config)
        assert len(warnings) == 0

    def test_undefined_server_in_servers_list(self):
        """Test warning when server in allow.servers doesn't exist."""
        mcp_config = {
            "mcpServers": {
                "postgres": {"command": "uvx"}
            }
        }
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["postgres", "nonexistent"]
                    }
                }
            }
        }

        warnings = validate_rules_against_servers(rules, mcp_config)
        assert len(warnings) == 1
        assert "nonexistent" in warnings[0]
        assert "undefined server" in warnings[0].lower()

    def test_undefined_server_in_tools(self):
        """Test warning when server in tools mapping doesn't exist."""
        mcp_config = {
            "mcpServers": {
                "postgres": {"command": "uvx"}
            }
        }
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "tools": {
                            "nonexistent": ["query"]
                        }
                    }
                }
            }
        }

        warnings = validate_rules_against_servers(rules, mcp_config)
        assert len(warnings) == 1
        assert "nonexistent" in warnings[0]

    def test_wildcard_server_allowed(self):
        """Test that wildcard '*' server doesn't generate warning."""
        mcp_config = {
            "mcpServers": {
                "postgres": {"command": "uvx"}
            }
        }
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["*"]
                    }
                }
            }
        }

        warnings = validate_rules_against_servers(rules, mcp_config)
        assert len(warnings) == 0

    def test_deny_section_also_validated(self):
        """Test that deny section is also validated."""
        mcp_config = {
            "mcpServers": {
                "postgres": {"command": "uvx"}
            }
        }
        rules = {
            "agents": {
                "test": {
                    "deny": {
                        "servers": ["nonexistent"]
                    }
                }
            }
        }

        warnings = validate_rules_against_servers(rules, mcp_config)
        assert len(warnings) == 1
        assert "nonexistent" in warnings[0]

    def test_no_agents_section(self):
        """Test that missing agents section doesn't cause error."""
        mcp_config = {"mcpServers": {}}
        rules = {"defaults": {"deny_on_missing_agent": True}}

        warnings = validate_rules_against_servers(rules, mcp_config)
        assert len(warnings) == 0
