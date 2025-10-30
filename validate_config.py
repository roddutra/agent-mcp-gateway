#!/usr/bin/env python3
"""Validate configuration files for Agent MCP Gateway."""

import sys
from pathlib import Path

from src.config import (
    load_mcp_config,
    load_gateway_rules,
    validate_rules_against_servers,
    get_config_path,
    get_mcp_config_path,
    get_gateway_rules_path,
)


def main():
    """Validate configuration files and report any issues."""
    print("Agent MCP Gateway - Configuration Validator\n")

    # Get config paths
    mcp_config_path = get_mcp_config_path()
    rules_path = get_gateway_rules_path()

    print(f"MCP Servers Config: {mcp_config_path}")
    print(f"Gateway Rules: {rules_path}\n")

    errors = []
    warnings = []

    # Load MCP server configuration
    try:
        print("Loading MCP server configuration...")
        mcp_config = load_mcp_config(mcp_config_path)
        servers = mcp_config.get("mcpServers", {})
        print(f"✓ Loaded {len(servers)} server(s):")
        for server_name, server_config in servers.items():
            transport = "stdio" if "command" in server_config else "HTTP"
            print(f"  - {server_name} ({transport})")
        print()
    except FileNotFoundError as e:
        errors.append(f"MCP config file not found: {e}")
        mcp_config = None
    except Exception as e:
        errors.append(f"Failed to load MCP config: {e}")
        mcp_config = None

    # Load gateway rules
    try:
        print("Loading gateway rules...")
        rules = load_gateway_rules(rules_path)
        agents = rules.get("agents", {})
        print(f"✓ Loaded {len(agents)} agent policy(ies):")
        for agent_id in agents.keys():
            print(f"  - {agent_id}")
        print()
    except FileNotFoundError as e:
        errors.append(f"Gateway rules file not found: {e}")
        rules = None
    except Exception as e:
        errors.append(f"Failed to load gateway rules: {e}")
        rules = None

    # Cross-validate rules against servers
    if mcp_config and rules:
        print("Cross-validating rules against servers...")
        cross_warnings = validate_rules_against_servers(rules, mcp_config)
        if cross_warnings:
            warnings.extend(cross_warnings)
            print(f"⚠ Found {len(cross_warnings)} warning(s)")
        else:
            print("✓ All rules reference valid servers")
        print()

    # Report results
    if errors:
        print("ERRORS:")
        for error in errors:
            print(f"  ✗ {error}")
        print()

    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"  ⚠ {warning}")
        print()

    if not errors and not warnings:
        print("✓ Configuration is valid and ready to use!\n")
        return 0
    elif errors:
        print("✗ Configuration has errors that must be fixed.\n")
        return 1
    else:
        print("✓ Configuration is valid but has warnings (review recommended).\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
