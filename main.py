"""Main entry point for Agent MCP Gateway."""

import asyncio
import logging
import os
import sys
from src.gateway import gateway, initialize_gateway
from src.config import load_mcp_config, load_gateway_rules, get_config_path, validate_rules_against_servers, reload_configs
from src.policy import PolicyEngine
from src.audit import AuditLogger
from src.proxy import ProxyManager
from src.metrics import MetricsCollector
from src.middleware import AgentAccessControl
from src.config_watcher import ConfigWatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Module-level storage for components (needed by reload callbacks)
_mcp_config_path: str = ""
_gateway_rules_path: str = ""
_policy_engine: PolicyEngine | None = None
_proxy_manager: ProxyManager | None = None
_config_watcher: ConfigWatcher | None = None


def on_mcp_config_changed(config_path: str) -> None:
    """Handle MCP server configuration file changes.

    This callback is invoked by ConfigWatcher when mcp-servers.json changes.
    It reloads and validates both configs (since they cross-reference each other),
    then reloads the ProxyManager if validation succeeds.

    Args:
        config_path: Absolute path to the changed MCP config file
    """
    logger.info(f"MCP server configuration file changed: {config_path}")
    # Also print to stderr so user definitely sees it
    print(f"\n[HOT RELOAD] Detected change in MCP server config file: {config_path}", file=sys.stderr)
    print(f"[HOT RELOAD] Reloading and validating new configuration...", file=sys.stderr)

    try:
        # Get the proxy_manager and gateway_rules_path from module globals
        if not _proxy_manager or not _gateway_rules_path:
            logger.error("Cannot reload: components not initialized")
            return

        # Load and validate both configs (reload_configs validates cross-references)
        mcp_config, gateway_rules, error = reload_configs(
            config_path,
            _gateway_rules_path
        )

        if error:
            logger.error(f"Failed to reload MCP server configuration: {error}")
            logger.info("Keeping existing MCP server configuration")
            return

        logger.info("MCP server configuration validated successfully")

        # Reload ProxyManager (async operation - need to handle from sync callback)
        # Since this callback runs in a watchdog thread and the gateway uses anyio,
        # we create a new asyncio event loop to run the async reload operation
        try:
            # Create a new event loop for this thread
            reload_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(reload_loop)

            try:
                # Run the async reload in this loop
                success, reload_error = reload_loop.run_until_complete(
                    _proxy_manager.reload(mcp_config)
                )

                if success:
                    logger.info("ProxyManager reloaded successfully")
                    print(f"[HOT RELOAD] MCP server configuration reloaded successfully", file=sys.stderr)
                    print(f"[HOT RELOAD] Proxy connections updated", file=sys.stderr)
                else:
                    logger.error(f"ProxyManager reload failed: {reload_error}")
                    logger.info("Keeping existing proxy connections")
                    print(f"[HOT RELOAD] ERROR: Failed to reload proxy manager: {reload_error}", file=sys.stderr)
            finally:
                # Clean up the event loop
                reload_loop.close()
        except Exception as e:
            logger.error(f"Error running ProxyManager reload: {e}")

    except Exception as e:
        logger.error(f"Unexpected error reloading MCP server configuration: {e}", exc_info=True)
        logger.info("Keeping existing MCP server configuration")


def on_gateway_rules_changed(rules_path: str) -> None:
    """Handle gateway rules configuration file changes.

    This callback is invoked by ConfigWatcher when gateway-rules.json changes.
    It reloads and validates both configs (since they cross-reference each other),
    then reloads the PolicyEngine if validation succeeds.

    Args:
        rules_path: Absolute path to the changed gateway rules file
    """
    logger.info(f"Gateway rules configuration file changed: {rules_path}")
    # Also print to stderr so user definitely sees it
    print(f"\n[HOT RELOAD] Detected change in gateway rules file: {rules_path}", file=sys.stderr)
    print(f"[HOT RELOAD] Reloading and validating new rules...", file=sys.stderr)

    try:
        # Get the policy_engine and mcp_config_path from module globals
        if not _policy_engine or not _mcp_config_path:
            logger.error("Cannot reload: components not initialized")
            return

        # Load and validate both configs (reload_configs validates cross-references)
        mcp_config, gateway_rules, error = reload_configs(
            _mcp_config_path,
            rules_path
        )

        if error:
            logger.error(f"Failed to reload gateway rules: {error}")
            logger.info("Keeping existing gateway rules")
            return

        logger.info("Gateway rules validated successfully")

        # Reload PolicyEngine (synchronous operation)
        success, reload_error = _policy_engine.reload(gateway_rules)
        if success:
            logger.info("PolicyEngine reloaded successfully")
            # Also print to stderr so user definitely sees it
            print(f"\n[HOT RELOAD] Gateway rules reloaded successfully at {rules_path}", file=sys.stderr)
            print(f"[HOT RELOAD] Policy changes are now active", file=sys.stderr)
        else:
            logger.error(f"PolicyEngine reload failed: {reload_error}")
            logger.info("Keeping existing policy rules")
            print(f"\n[HOT RELOAD] ERROR: Failed to reload gateway rules: {reload_error}", file=sys.stderr)

    except Exception as e:
        logger.error(f"Unexpected error reloading gateway rules: {e}", exc_info=True)
        logger.info("Keeping existing gateway rules")


def main():
    """Initialize and run the Agent MCP Gateway."""
    global _mcp_config_path, _gateway_rules_path, _policy_engine, _proxy_manager, _config_watcher

    try:
        # Get configuration file paths from environment or use defaults
        _mcp_config_path = get_config_path("GATEWAY_MCP_CONFIG", "./config/mcp-servers.json")
        _gateway_rules_path = get_config_path("GATEWAY_RULES", "./config/gateway-rules.json")
        audit_log_path = os.environ.get("GATEWAY_AUDIT_LOG", "./logs/audit.jsonl")

        print(f"Loading MCP server configuration from: {_mcp_config_path}", file=sys.stderr)
        print(f"Loading gateway rules from: {_gateway_rules_path}", file=sys.stderr)
        print(f"Audit log will be written to: {audit_log_path}", file=sys.stderr)

        # Load configurations
        mcp_config = load_mcp_config(_mcp_config_path)
        gateway_rules = load_gateway_rules(_gateway_rules_path)

        # Validate that all servers referenced in rules exist
        warnings = validate_rules_against_servers(gateway_rules, mcp_config)
        if warnings:
            print("\nConfiguration warnings:", file=sys.stderr)
            for warning in warnings:
                print(f"  - {warning}", file=sys.stderr)
            print(file=sys.stderr)

        # Initialize policy engine
        _policy_engine = PolicyEngine(gateway_rules)

        # Initialize audit logger
        audit_logger = AuditLogger(audit_log_path)

        # Initialize proxy manager
        print("\nInitializing proxy connections to downstream servers...", file=sys.stderr)
        _proxy_manager = ProxyManager()

        try:
            _proxy_manager.initialize_connections(mcp_config)

            # Log proxy status
            all_servers = _proxy_manager.get_all_servers()
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
        access_control = AgentAccessControl(_policy_engine)
        gateway.add_middleware(access_control)
        print(f"  - Access control middleware registered", file=sys.stderr)

        # Initialize gateway with all components
        initialize_gateway(_policy_engine, mcp_config, _proxy_manager)

        # Initialize ConfigWatcher for hot reloading
        try:
            _config_watcher = ConfigWatcher(
                mcp_config_path=_mcp_config_path,
                gateway_rules_path=_gateway_rules_path,
                on_mcp_config_changed=on_mcp_config_changed,
                on_gateway_rules_changed=on_gateway_rules_changed,
                debounce_seconds=0.3
            )
            _config_watcher.start()
            print(f"  - Configuration file watching enabled (hot reload)", file=sys.stderr)
        except Exception as e:
            print(f"  - Warning: Could not start config file watcher: {e}", file=sys.stderr)
            print(f"  - Hot reload disabled, but gateway will continue normally", file=sys.stderr)

        # Log successful initialization
        print(f"\nAgent MCP Gateway initialized successfully", file=sys.stderr)
        print(f"  - {len(mcp_config.get('mcpServers', {}))} MCP server(s) configured", file=sys.stderr)
        print(f"  - {len(gateway_rules.get('agents', {}))} agent(s) configured", file=sys.stderr)
        print(f"  - Default policy: {'deny' if gateway_rules.get('defaults', {}).get('deny_on_missing_agent', True) else 'allow'} unknown agents", file=sys.stderr)
        print(f"  - 3 gateway tools available: list_servers, get_server_tools, execute_tool", file=sys.stderr)
        print("\nGateway is ready. Running with stdio transport...\n", file=sys.stderr)

        # Run gateway with stdio transport (default)
        try:
            gateway.run()
        finally:
            # Clean up ConfigWatcher on shutdown
            if _config_watcher:
                logger.info("Stopping configuration file watcher...")
                _config_watcher.stop()

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
