"""Main entry point for Agent MCP Gateway."""

import os
import sys
from src.gateway import gateway, initialize_gateway
from src.config import load_mcp_config, load_gateway_rules, get_config_path, validate_rules_against_servers
from src.policy import PolicyEngine
from src.audit import AuditLogger
from src.proxy import ProxyManager
from src.metrics import MetricsCollector
from src.middleware import AgentAccessControl


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

        # Initialize proxy manager
        print("\nInitializing proxy connections to downstream servers...", file=sys.stderr)
        proxy_manager = ProxyManager()

        try:
            proxy_manager.initialize_connections(mcp_config)

            # Log proxy status
            all_servers = proxy_manager.get_all_servers()
            print(f"  - {len(all_servers)} proxy client(s) initialized", file=sys.stderr)
            for server in all_servers:
                status = "ready" if server["status"] == "initialized" else "error"
                print(f"    * {server['name']}: {status}", file=sys.stderr)
        except Exception as e:
            print(f"  - Warning: Proxy initialization encountered errors: {e}", file=sys.stderr)
            print(f"  - Gateway will continue, but downstream tools may be unavailable", file=sys.stderr)

        # Initialize metrics collector
        metrics_collector = MetricsCollector()
        print(f"  - Metrics collector initialized", file=sys.stderr)

        # Create and register middleware
        access_control = AgentAccessControl(policy_engine)
        gateway.add_middleware(access_control)
        print(f"  - Access control middleware registered", file=sys.stderr)

        # Initialize gateway with all components
        initialize_gateway(policy_engine, mcp_config, proxy_manager)

        # Log successful initialization
        print(f"\nAgent MCP Gateway initialized successfully", file=sys.stderr)
        print(f"  - {len(mcp_config.get('mcpServers', {}))} MCP server(s) configured", file=sys.stderr)
        print(f"  - {len(gateway_rules.get('agents', {}))} agent(s) configured", file=sys.stderr)
        print(f"  - Default policy: {'deny' if gateway_rules.get('defaults', {}).get('deny_on_missing_agent', True) else 'allow'} unknown agents", file=sys.stderr)
        print(f"  - 3 gateway tools available: list_servers, get_server_tools, execute_tool", file=sys.stderr)
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
