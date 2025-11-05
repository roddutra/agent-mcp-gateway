"""Main entry point for Agent MCP Gateway."""

import argparse
import asyncio
import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from typing import Optional
from .gateway import gateway, initialize_gateway
from .config import load_mcp_config, load_gateway_rules, get_mcp_config_path, get_gateway_rules_path, validate_rules_against_servers, reload_configs
from .policy import PolicyEngine
from .audit import AuditLogger
from .proxy import ProxyManager
from .metrics import MetricsCollector
from .middleware import AgentAccessControl
from .config_watcher import ConfigWatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

# Add file-based debug logging for MCP Inspector scenarios
# (Inspector captures stdout/stderr, so we need a separate log file)
debug_log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gateway-debug.log')
debug_handler = logging.FileHandler(debug_log_path, mode='w')  # Overwrite on each start
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
debug_handler.setFormatter(debug_formatter)

# Add to root logger
root_logger = logging.getLogger()
root_logger.addHandler(debug_handler)
root_logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)
logger.debug(f"Debug logging initialized - writing to: {debug_log_path}")

# Module-level storage for components (needed by reload callbacks)
_mcp_config_path: str = ""
_gateway_rules_path: str = ""
_policy_engine: PolicyEngine | None = None
_proxy_manager: ProxyManager | None = None
_config_watcher: ConfigWatcher | None = None

# Track last modification times for fallback reload checking
_last_mcp_config_mtime: float = 0.0
_last_gateway_rules_mtime: float = 0.0

# Hot reload status tracking
_reload_status_lock = threading.Lock()
_mcp_config_reload_status = {
    "last_attempt": None,  # datetime
    "last_success": None,  # datetime
    "last_error": None,    # str or None
    "attempt_count": 0,
    "success_count": 0,
}
_gateway_rules_reload_status = {
    "last_attempt": None,  # datetime
    "last_success": None,  # datetime
    "last_error": None,    # str or None
    "attempt_count": 0,
    "success_count": 0,
    "last_warnings": [],   # list[str]
}


def check_config_changes() -> None:
    """Check if config files have changed and trigger reload if needed.

    This is a fallback mechanism in case file watching doesn't work (e.g., when
    running through MCP Inspector). It checks file modification times and triggers
    reload callbacks if files have changed since last check.
    """
    global _last_mcp_config_mtime, _last_gateway_rules_mtime

    try:
        # Check MCP config
        if os.path.exists(_mcp_config_path):
            current_mtime = os.path.getmtime(_mcp_config_path)
            if _last_mcp_config_mtime > 0 and current_mtime > _last_mcp_config_mtime:
                logger.debug(f"Detected MCP config change via mtime check: {current_mtime} > {_last_mcp_config_mtime}")
                on_mcp_config_changed(_mcp_config_path)
            _last_mcp_config_mtime = current_mtime

        # Check gateway rules
        if os.path.exists(_gateway_rules_path):
            current_mtime = os.path.getmtime(_gateway_rules_path)
            if _last_gateway_rules_mtime > 0 and current_mtime > _last_gateway_rules_mtime:
                logger.debug(f"Detected gateway rules change via mtime check: {current_mtime} > {_last_gateway_rules_mtime}")
                on_gateway_rules_changed(_gateway_rules_path)
            _last_gateway_rules_mtime = current_mtime
    except Exception as e:
        logger.debug(f"Error checking config changes: {e}")


def on_mcp_config_changed(config_path: str) -> None:
    """Handle MCP server configuration file changes.

    This callback is invoked by ConfigWatcher when .mcp.json changes.
    It reloads and validates both configs (since they cross-reference each other),
    then reloads the ProxyManager if validation succeeds.

    Args:
        config_path: Absolute path to the changed MCP config file
    """
    import time

    # Record reload attempt
    with _reload_status_lock:
        _mcp_config_reload_status["last_attempt"] = datetime.now()
        _mcp_config_reload_status["attempt_count"] += 1

    logger.debug(f"!!! CALLBACK TRIGGERED !!! on_mcp_config_changed called")
    logger.debug(f"  - config_path: {config_path}")
    logger.debug(f"  - current time: {time.time()}")
    logger.debug(f"  - thread: {threading.current_thread().name}")

    logger.info(f"MCP server configuration file changed: {config_path}")
    # Also print to stderr so user definitely sees it
    print(f"\n[HOT RELOAD] Detected change in MCP server config file: {config_path}", file=sys.stderr)
    print(f"[HOT RELOAD] Timestamp: {datetime.now().isoformat()}", file=sys.stderr)
    print(f"[HOT RELOAD] Reloading and validating new configuration...", file=sys.stderr)

    try:
        # Get the proxy_manager and gateway_rules_path from module globals
        if not _proxy_manager or not _gateway_rules_path:
            error_msg = "Cannot reload: components not initialized"
            logger.error(error_msg)
            with _reload_status_lock:
                _mcp_config_reload_status["last_error"] = error_msg
            return

        # Load and validate both configs (reload_configs validates cross-references)
        mcp_config, gateway_rules, error = reload_configs(
            config_path,
            _gateway_rules_path
        )

        if error:
            logger.error(f"Failed to reload MCP server configuration: {error}")
            logger.info("Keeping existing MCP server configuration")
            with _reload_status_lock:
                _mcp_config_reload_status["last_error"] = error
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

                    # Record success
                    with _reload_status_lock:
                        _mcp_config_reload_status["last_success"] = datetime.now()
                        _mcp_config_reload_status["last_error"] = None
                        _mcp_config_reload_status["success_count"] += 1
                else:
                    logger.error(f"ProxyManager reload failed: {reload_error}")
                    logger.info("Keeping existing proxy connections")
                    print(f"[HOT RELOAD] ERROR: Failed to reload proxy manager: {reload_error}", file=sys.stderr)

                    # Record error
                    with _reload_status_lock:
                        _mcp_config_reload_status["last_error"] = f"ProxyManager reload failed: {reload_error}"
            finally:
                # Clean up the event loop
                reload_loop.close()
        except Exception as e:
            error_msg = f"Error running ProxyManager reload: {e}"
            logger.error(error_msg)
            with _reload_status_lock:
                _mcp_config_reload_status["last_error"] = error_msg

    except Exception as e:
        error_msg = f"Unexpected error reloading MCP server configuration: {e}"
        logger.error(error_msg, exc_info=True)
        logger.info("Keeping existing MCP server configuration")
        with _reload_status_lock:
            _mcp_config_reload_status["last_error"] = error_msg


def on_gateway_rules_changed(rules_path: str) -> None:
    """Handle gateway rules configuration file changes.

    This callback is invoked by ConfigWatcher when .mcp-gateway-rules.json changes.
    It reloads and validates both configs (since they cross-reference each other),
    then reloads the PolicyEngine if validation succeeds.

    Args:
        rules_path: Absolute path to the changed gateway rules file
    """
    import time

    # Record reload attempt
    with _reload_status_lock:
        _gateway_rules_reload_status["last_attempt"] = datetime.now()
        _gateway_rules_reload_status["attempt_count"] += 1

    logger.debug(f"!!! CALLBACK TRIGGERED !!! on_gateway_rules_changed called")
    logger.debug(f"  - rules_path: {rules_path}")
    logger.debug(f"  - current time: {time.time()}")
    logger.debug(f"  - thread: {threading.current_thread().name}")

    logger.info(f"Gateway rules configuration file changed: {rules_path}")
    # Also print to stderr so user definitely sees it
    print(f"\n[HOT RELOAD] Detected change in gateway rules file: {rules_path}", file=sys.stderr)
    print(f"[HOT RELOAD] Timestamp: {datetime.now().isoformat()}", file=sys.stderr)
    print(f"[HOT RELOAD] Reloading and validating new rules...", file=sys.stderr)

    try:
        # Get the policy_engine and mcp_config_path from module globals
        if not _policy_engine or not _mcp_config_path:
            error_msg = "Cannot reload: components not initialized"
            logger.error(error_msg)
            with _reload_status_lock:
                _gateway_rules_reload_status["last_error"] = error_msg
            return

        # Load and validate both configs (reload_configs validates cross-references)
        mcp_config, gateway_rules, error = reload_configs(
            _mcp_config_path,
            rules_path
        )

        if error:
            logger.error(f"Failed to reload gateway rules: {error}")
            logger.info("Keeping existing gateway rules")
            with _reload_status_lock:
                _gateway_rules_reload_status["last_error"] = error
            return

        logger.info("Gateway rules validated successfully")

        # Check for validation warnings
        warnings = validate_rules_against_servers(gateway_rules, mcp_config)

        # Reload PolicyEngine (synchronous operation)
        success, reload_error = _policy_engine.reload(gateway_rules)
        if success:
            logger.info("PolicyEngine reloaded successfully")
            # Also print to stderr so user definitely sees it
            print(f"\n[HOT RELOAD] Gateway rules reloaded successfully at {rules_path}", file=sys.stderr)
            print(f"[HOT RELOAD] Policy changes are now active", file=sys.stderr)

            # If we got warnings, show them prominently
            if warnings:
                print(f"\n[HOT RELOAD WARNING] Configuration references undefined servers:", file=sys.stderr)
                for warning in warnings:
                    print(f"  - {warning}", file=sys.stderr)
                print(f"[HOT RELOAD WARNING] These rules will be ignored until servers are added", file=sys.stderr)

            # Record success
            with _reload_status_lock:
                _gateway_rules_reload_status["last_success"] = datetime.now()
                _gateway_rules_reload_status["last_error"] = None
                _gateway_rules_reload_status["success_count"] += 1
                _gateway_rules_reload_status["last_warnings"] = warnings
        else:
            logger.error(f"PolicyEngine reload failed: {reload_error}")
            logger.info("Keeping existing policy rules")
            print(f"\n[HOT RELOAD] ERROR: Failed to reload gateway rules: {reload_error}", file=sys.stderr)

            # Record error
            with _reload_status_lock:
                _gateway_rules_reload_status["last_error"] = f"PolicyEngine reload failed: {reload_error}"

    except Exception as e:
        error_msg = f"Unexpected error reloading gateway rules: {e}"
        logger.error(error_msg, exc_info=True)
        logger.info("Keeping existing gateway rules")
        with _reload_status_lock:
            _gateway_rules_reload_status["last_error"] = error_msg


def get_reload_status() -> dict:
    """Get current hot reload status for diagnostics.

    Returns:
        Dictionary containing reload status for both config files,
        including attempt/success timestamps, error messages, and warnings.
    """
    with _reload_status_lock:
        return {
            "mcp_config": _mcp_config_reload_status.copy(),
            "gateway_rules": _gateway_rules_reload_status.copy(),
        }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed command line arguments including debug flag
    """
    parser = argparse.ArgumentParser(
        description="Agent MCP Gateway - Policy-based proxy for MCP servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (exposes get_gateway_status tool for diagnostics)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="agent-mcp-gateway 0.1.0"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create config directory at ~/.config/agent-mcp-gateway/ with example files"
    )
    return parser.parse_args()


def init_config_directory() -> None:
    """Create config directory with example configuration files."""
    from pathlib import Path
    import shutil

    config_dir = Path.home() / ".config" / "agent-mcp-gateway"

    # Check if directory already exists
    if config_dir.exists():
        response = input(f"Config directory already exists at {config_dir}. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Initialization cancelled.")
            return

    # Create directory
    config_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created config directory: {config_dir}")

    # Copy example configs from src/config/ directory
    # When installed, they're in site-packages/src/config/
    # When running from source, they're in src/config/
    config_dir_path = Path(__file__).parent / "config"
    source_mcp = config_dir_path / ".mcp.json.example"
    source_rules = config_dir_path / ".mcp-gateway-rules.json.example"

    dest_mcp = config_dir / "mcp.json"
    dest_rules = config_dir / "mcp-gateway-rules.json"

    if source_mcp.exists():
        shutil.copy(source_mcp, dest_mcp)
        print(f"Created: {dest_mcp}")
    else:
        print(f"Warning: Example config not found at {source_mcp}")

    if source_rules.exists():
        shutil.copy(source_rules, dest_rules)
        print(f"Created: {dest_rules}")
    else:
        print(f"Warning: Example rules not found at {source_rules}")

    print(f"\nConfiguration initialized!")
    print(f"Edit configs at: {config_dir}")
    print(f"\nTo use these configs, run:")
    print(f"  GATEWAY_MCP_CONFIG={dest_mcp} \\")
    print(f"  GATEWAY_RULES={dest_rules} \\")
    print(f"  agent-mcp-gateway")


def main():
    """Initialize and run the Agent MCP Gateway."""
    global _mcp_config_path, _gateway_rules_path, _policy_engine, _proxy_manager, _config_watcher
    global _last_mcp_config_mtime, _last_gateway_rules_mtime

    # Parse command line arguments
    args = parse_args()

    # Handle --init command
    if args.init:
        init_config_directory()
        sys.exit(0)

    # Check for debug mode from environment variable or CLI argument
    # CLI argument takes precedence over environment variable
    debug_mode = args.debug or os.getenv("GATEWAY_DEBUG", "").lower() in ("true", "1", "yes")

    try:
        # Get configuration file paths from environment or use defaults
        _mcp_config_path = get_mcp_config_path()
        _gateway_rules_path = get_gateway_rules_path()
        audit_log_path = os.environ.get("GATEWAY_AUDIT_LOG", "./logs/audit.jsonl")

        # Get default agent ID for fallback chain (optional)
        default_agent_id = os.getenv("GATEWAY_DEFAULT_AGENT")

        # Initialize modification times for fallback reload checking
        if os.path.exists(_mcp_config_path):
            _last_mcp_config_mtime = os.path.getmtime(_mcp_config_path)
        if os.path.exists(_gateway_rules_path):
            _last_gateway_rules_mtime = os.path.getmtime(_gateway_rules_path)

        print(f"Loading MCP server configuration from: {_mcp_config_path}", file=sys.stderr)
        print(f"Loading gateway rules from: {_gateway_rules_path}", file=sys.stderr)
        print(f"Audit log will be written to: {audit_log_path}", file=sys.stderr)
        if default_agent_id:
            print(f"Default agent for fallback chain: {default_agent_id}", file=sys.stderr)
        if debug_mode:
            print(f"Debug mode: ENABLED (get_gateway_status tool available)", file=sys.stderr)
        else:
            print(f"Debug mode: DISABLED (use --debug or GATEWAY_DEBUG=true to enable)", file=sys.stderr)

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
            for server_name in all_servers:
                # get_all_servers() returns list of server names (strings), not dicts
                status = "ready"  # If it's in the list, it was initialized
                print(f"    * {server_name}: {status}", file=sys.stderr)
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
        initialize_gateway(
            _policy_engine,
            mcp_config,
            _proxy_manager,
            check_config_changes,
            get_reload_status,
            default_agent_id,
            debug_mode
        )

        # Initialize ConfigWatcher for hot reloading
        logger.debug("=== ConfigWatcher Initialization Starting ===")
        logger.debug(f"MCP config path: {_mcp_config_path}")
        logger.debug(f"MCP config path (absolute): {os.path.abspath(_mcp_config_path)}")
        logger.debug(f"MCP config exists: {os.path.exists(_mcp_config_path)}")
        logger.debug(f"Gateway rules path: {_gateway_rules_path}")
        logger.debug(f"Gateway rules path (absolute): {os.path.abspath(_gateway_rules_path)}")
        logger.debug(f"Gateway rules exists: {os.path.exists(_gateway_rules_path)}")
        logger.debug(f"on_mcp_config_changed callback: {on_mcp_config_changed}")
        logger.debug(f"on_gateway_rules_changed callback: {on_gateway_rules_changed}")

        try:
            _config_watcher = ConfigWatcher(
                mcp_config_path=_mcp_config_path,
                gateway_rules_path=_gateway_rules_path,
                on_mcp_config_changed=on_mcp_config_changed,
                on_gateway_rules_changed=on_gateway_rules_changed,
                debounce_seconds=0.3
            )
            logger.debug("ConfigWatcher instance created successfully")

            _config_watcher.start()
            logger.debug("ConfigWatcher.start() called successfully")

            # Check if observer is running
            if hasattr(_config_watcher, 'observer') and _config_watcher.observer:
                logger.debug(f"Observer is alive: {_config_watcher.observer.is_alive()}")
                logger.debug(f"Observer thread: {_config_watcher.observer}")
            else:
                logger.warning("Observer not initialized or None")

            print(f"  - Configuration file watching enabled (hot reload)", file=sys.stderr)
            logger.debug("=== ConfigWatcher Initialization Complete ===")

        except Exception as e:
            logger.error(f"FAILED to initialize ConfigWatcher: {e}", exc_info=True)
            print(f"  - Warning: Could not start config file watcher: {e}", file=sys.stderr)
            print(f"  - Hot reload disabled, but gateway will continue normally", file=sys.stderr)

        # Log successful initialization
        print(f"\nAgent MCP Gateway initialized successfully", file=sys.stderr)
        print(f"  - {len(mcp_config.get('mcpServers', {}))} MCP server(s) configured", file=sys.stderr)
        print(f"  - {len(gateway_rules.get('agents', {}))} agent(s) configured", file=sys.stderr)
        print(f"  - Default policy: {'deny' if gateway_rules.get('defaults', {}).get('deny_on_missing_agent', True) else 'allow'} unknown agents", file=sys.stderr)
        if debug_mode:
            print(f"  - 4 gateway tools available: list_servers, get_server_tools, execute_tool, get_gateway_status", file=sys.stderr)
        else:
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
