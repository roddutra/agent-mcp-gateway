"""Configuration management for Agent MCP Gateway."""

import json
import os
import re
from pathlib import Path
from typing import Any


def load_mcp_config(path: str) -> dict:
    """Load and validate MCP server configuration.

    Args:
        path: Path to MCP servers configuration file

    Returns:
        Dictionary containing mcpServers configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid or malformed
        json.JSONDecodeError: If config is not valid JSON
    """
    # Expand user paths and convert to absolute
    config_path = Path(path).expanduser().resolve()

    # Check if file exists
    if not config_path.exists():
        raise FileNotFoundError(
            f"MCP server configuration file not found: {config_path}"
        )

    # Load JSON
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in MCP server configuration: {e.msg}",
            e.doc,
            e.pos
        )

    # Validate top-level structure
    if not isinstance(config, dict):
        raise ValueError(
            f"MCP server configuration must be a JSON object, got {type(config).__name__}"
        )

    if "mcpServers" not in config:
        raise ValueError(
            'MCP server configuration must contain "mcpServers" key'
        )

    mcp_servers = config["mcpServers"]
    if not isinstance(mcp_servers, dict):
        raise ValueError(
            f'"mcpServers" must be an object, got {type(mcp_servers).__name__}'
        )

    # Validate each server configuration
    for server_name, server_config in mcp_servers.items():
        if not isinstance(server_config, dict):
            raise ValueError(
                f'Server "{server_name}" configuration must be an object, '
                f'got {type(server_config).__name__}'
            )

        # Determine transport type and validate required fields
        has_command = "command" in server_config
        has_url = "url" in server_config

        if has_command and has_url:
            raise ValueError(
                f'Server "{server_name}" cannot have both "command" (stdio) '
                f'and "url" (HTTP) - specify one transport type only'
            )

        if not has_command and not has_url:
            raise ValueError(
                f'Server "{server_name}" must specify either "command" (stdio) '
                f'or "url" (HTTP) transport'
            )

        # Validate stdio transport
        if has_command:
            if not isinstance(server_config["command"], str):
                raise ValueError(
                    f'Server "{server_name}": "command" must be a string, '
                    f'got {type(server_config["command"]).__name__}'
                )

            if "args" in server_config:
                if not isinstance(server_config["args"], list):
                    raise ValueError(
                        f'Server "{server_name}": "args" must be an array, '
                        f'got {type(server_config["args"]).__name__}'
                    )

                for i, arg in enumerate(server_config["args"]):
                    if not isinstance(arg, str):
                        raise ValueError(
                            f'Server "{server_name}": args[{i}] must be a string, '
                            f'got {type(arg).__name__}'
                        )

            if "env" in server_config:
                if not isinstance(server_config["env"], dict):
                    raise ValueError(
                        f'Server "{server_name}": "env" must be an object, '
                        f'got {type(server_config["env"]).__name__}'
                    )

                for key, value in server_config["env"].items():
                    if not isinstance(value, str):
                        raise ValueError(
                            f'Server "{server_name}": env["{key}"] must be a string, '
                            f'got {type(value).__name__}'
                        )

        # Validate HTTP transport
        if has_url:
            if not isinstance(server_config["url"], str):
                raise ValueError(
                    f'Server "{server_name}": "url" must be a string, '
                    f'got {type(server_config["url"]).__name__}'
                )

            # Basic URL validation
            url = server_config["url"]
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError(
                    f'Server "{server_name}": "url" must start with http:// or https://, '
                    f'got "{url}"'
                )

            if "headers" in server_config:
                if not isinstance(server_config["headers"], dict):
                    raise ValueError(
                        f'Server "{server_name}": "headers" must be an object, '
                        f'got {type(server_config["headers"]).__name__}'
                    )

                for key, value in server_config["headers"].items():
                    if not isinstance(value, str):
                        raise ValueError(
                            f'Server "{server_name}": headers["{key}"] must be a string, '
                            f'got {type(value).__name__}'
                        )

    # Perform environment variable substitution
    config = _substitute_env_vars(config)

    return config


def load_gateway_rules(path: str) -> dict:
    """Load and validate gateway rules configuration.

    Args:
        path: Path to gateway rules configuration file

    Returns:
        Dictionary containing agent policies and defaults

    Raises:
        FileNotFoundError: If rules file doesn't exist
        ValueError: If rules are invalid or malformed
        json.JSONDecodeError: If rules are not valid JSON
    """
    # Expand user paths and convert to absolute
    rules_path = Path(path).expanduser().resolve()

    # Check if file exists
    if not rules_path.exists():
        raise FileNotFoundError(
            f"Gateway rules configuration file not found: {rules_path}"
        )

    # Load JSON
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in gateway rules configuration: {e.msg}",
            e.doc,
            e.pos
        )

    # Validate top-level structure
    if not isinstance(rules, dict):
        raise ValueError(
            f"Gateway rules configuration must be a JSON object, got {type(rules).__name__}"
        )

    # Validate agents section
    if "agents" in rules:
        agents = rules["agents"]
        if not isinstance(agents, dict):
            raise ValueError(
                f'"agents" must be an object, got {type(agents).__name__}'
            )

        for agent_id, agent_config in agents.items():
            # Validate agent ID format (support hierarchical: team.role)
            if not isinstance(agent_id, str) or not agent_id:
                raise ValueError(
                    f"Agent ID must be a non-empty string, got {repr(agent_id)}"
                )

            if not re.match(r'^[a-zA-Z0-9_.-]+$', agent_id):
                raise ValueError(
                    f'Agent ID "{agent_id}" contains invalid characters. '
                    f'Only alphanumeric, underscore, dot, and hyphen allowed.'
                )

            if not isinstance(agent_config, dict):
                raise ValueError(
                    f'Agent "{agent_id}" configuration must be an object, '
                    f'got {type(agent_config).__name__}'
                )

            # Validate allow/deny sections
            for section in ["allow", "deny"]:
                if section not in agent_config:
                    continue

                section_config = agent_config[section]
                if not isinstance(section_config, dict):
                    raise ValueError(
                        f'Agent "{agent_id}" {section} section must be an object, '
                        f'got {type(section_config).__name__}'
                    )

                # Validate servers list
                if "servers" in section_config:
                    servers = section_config["servers"]
                    if not isinstance(servers, list):
                        raise ValueError(
                            f'Agent "{agent_id}" {section}.servers must be an array, '
                            f'got {type(servers).__name__}'
                        )

                    for i, server in enumerate(servers):
                        if not isinstance(server, str):
                            raise ValueError(
                                f'Agent "{agent_id}" {section}.servers[{i}] must be a string, '
                                f'got {type(server).__name__}'
                            )

                        # Validate wildcard patterns
                        if '*' in server and server != '*':
                            raise ValueError(
                                f'Agent "{agent_id}" {section}.servers[{i}]: '
                                f'wildcard "*" can only be used alone, not in patterns'
                            )

                # Validate tools mapping
                if "tools" in section_config:
                    tools = section_config["tools"]
                    if not isinstance(tools, dict):
                        raise ValueError(
                            f'Agent "{agent_id}" {section}.tools must be an object, '
                            f'got {type(tools).__name__}'
                        )

                    for server_name, tool_patterns in tools.items():
                        if not isinstance(tool_patterns, list):
                            raise ValueError(
                                f'Agent "{agent_id}" {section}.tools["{server_name}"] '
                                f'must be an array, got {type(tool_patterns).__name__}'
                            )

                        for i, pattern in enumerate(tool_patterns):
                            if not isinstance(pattern, str):
                                raise ValueError(
                                    f'Agent "{agent_id}" {section}.tools["{server_name}"][{i}] '
                                    f'must be a string, got {type(pattern).__name__}'
                                )

                            # Validate wildcard patterns (support get_*, *, *_query, etc.)
                            if '*' in pattern:
                                # Ensure only one wildcard and it's either alone or at start/end
                                wildcard_count = pattern.count('*')
                                if wildcard_count > 1:
                                    raise ValueError(
                                        f'Agent "{agent_id}" {section}.tools["{server_name}"][{i}]: '
                                        f'pattern "{pattern}" contains multiple wildcards - only one allowed'
                                    )

                                if pattern != '*' and not (pattern.startswith('*') or pattern.endswith('*')):
                                    raise ValueError(
                                        f'Agent "{agent_id}" {section}.tools["{server_name}"][{i}]: '
                                        f'wildcard in pattern "{pattern}" must be at start, end, or alone'
                                    )

    # Validate defaults section
    if "defaults" in rules:
        defaults = rules["defaults"]
        if not isinstance(defaults, dict):
            raise ValueError(
                f'"defaults" must be an object, got {type(defaults).__name__}'
            )

        if "deny_on_missing_agent" in defaults:
            deny_on_missing = defaults["deny_on_missing_agent"]
            if not isinstance(deny_on_missing, bool):
                raise ValueError(
                    f'"defaults.deny_on_missing_agent" must be a boolean, '
                    f'got {type(deny_on_missing).__name__}'
                )

    return rules


def _substitute_env_vars(obj: Any) -> Any:
    """Recursively substitute ${VAR} with environment variables.

    Args:
        obj: Object to process (str, dict, list, or other)

    Returns:
        Object with environment variables substituted

    Raises:
        ValueError: If referenced environment variable is not set
    """
    if isinstance(obj, str):
        # Find all ${VAR} patterns
        pattern = re.compile(r'\$\{([^}]+)\}')

        def replace_var(match):
            var_name = match.group(1)
            if var_name not in os.environ:
                raise ValueError(
                    f'Environment variable "{var_name}" referenced in configuration '
                    f'but not set. Please set this variable before starting the gateway.'
                )
            return os.environ[var_name]

        return pattern.sub(replace_var, obj)

    elif isinstance(obj, dict):
        return {key: _substitute_env_vars(value) for key, value in obj.items()}

    elif isinstance(obj, list):
        return [_substitute_env_vars(item) for item in obj]

    else:
        # Return other types unchanged (int, bool, None, etc.)
        return obj


def get_config_path(env_var: str, default: str) -> str:
    """Get configuration file path from environment variable or use default.

    Args:
        env_var: Environment variable name to check
        default: Default path if environment variable not set

    Returns:
        Resolved configuration file path
    """
    path = os.environ.get(env_var, default)
    return str(Path(path).expanduser().resolve())


def validate_rules_against_servers(rules: dict, mcp_config: dict) -> list[str]:
    """Validate that all servers referenced in rules exist in MCP config.

    Args:
        rules: Gateway rules configuration
        mcp_config: MCP servers configuration

    Returns:
        List of warning messages (empty if all valid)
    """
    warnings = []

    if "agents" not in rules:
        return warnings

    available_servers = set(mcp_config.get("mcpServers", {}).keys())

    for agent_id, agent_config in rules["agents"].items():
        for section in ["allow", "deny"]:
            if section not in agent_config:
                continue

            section_config = agent_config[section]

            # Check servers list
            if "servers" in section_config:
                for server in section_config["servers"]:
                    if server != "*" and server not in available_servers:
                        warnings.append(
                            f'Agent "{agent_id}" {section}.servers references '
                            f'undefined server "{server}"'
                        )

            # Check tools mapping
            if "tools" in section_config:
                for server_name in section_config["tools"].keys():
                    if server_name not in available_servers:
                        warnings.append(
                            f'Agent "{agent_id}" {section}.tools references '
                            f'undefined server "{server_name}"'
                        )

    return warnings
