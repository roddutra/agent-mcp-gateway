"""Main entry point for Agent MCP Gateway."""

import os
import sys
from src.gateway import gateway, initialize_gateway
from src.config import load_mcp_config, load_gateway_rules, get_config_path, validate_rules_against_servers
from src.policy import PolicyEngine
from src.audit import AuditLogger


def main():
    """Initialize and run the Agent MCP Gateway."""
    try:
        # Get configuration file paths from environment or use defaults
        mcp_config_path = get_config_path("GATEWAY_MCP_CONFIG", "./config/mcp-servers.json")
        rules_path = get_config_path("GATEWAY_RULES", "./config/gateway-rules.json")
        audit_log_path = os.environ.get("GATEWAY_AUDIT_LOG", "./logs/audit.jsonl")

        print(f"Loading MCP server configuration from: {mcp_config_path}", file=sys.stderr)
        print(f"Loading gateway rules from: {rules_path}", file=sys.stderr)
        print(f"Audit log will be written to: {audit_log_path}", file=sys.stderr)

        # Load configurations
        mcp_config = load_mcp_config(mcp_config_path)
        gateway_rules = load_gateway_rules(rules_path)

        # Validate that all servers referenced in rules exist
        warnings = validate_rules_against_servers(gateway_rules, mcp_config)
        if warnings:
            print("\nConfiguration warnings:", file=sys.stderr)
            for warning in warnings:
                print(f"  - {warning}", file=sys.stderr)
            print(file=sys.stderr)

        # Initialize policy engine
        policy_engine = PolicyEngine(gateway_rules)

        # Initialize audit logger
        audit_logger = AuditLogger(audit_log_path)

        # Initialize gateway with configurations
        initialize_gateway(policy_engine, mcp_config)

        # Log successful initialization
        print(f"\nAgent MCP Gateway initialized successfully", file=sys.stderr)
        print(f"  - {len(mcp_config.get('mcpServers', {}))} MCP servers configured", file=sys.stderr)
        print(f"  - {len(gateway_rules.get('agents', {}))} agents configured", file=sys.stderr)
        print(f"  - Default policy: {'deny' if gateway_rules.get('defaults', {}).get('deny_on_missing_agent', True) else 'allow'} unknown agents", file=sys.stderr)
        print("\nGateway is ready. Running with stdio transport...\n", file=sys.stderr)

        # Run gateway with stdio transport (default)
        gateway.run()

    except FileNotFoundError as e:
        print(f"\nERROR: Configuration file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"\nERROR: Invalid configuration: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Failed to start gateway: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
