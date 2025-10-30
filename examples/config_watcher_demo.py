"""Demo script showing ConfigWatcher usage.

This script demonstrates how to use the ConfigWatcher to monitor
configuration files for changes. It sets up logging and creates
a watcher with callback functions.

Usage:
    python examples/config_watcher_demo.py

Then modify .mcp.json or .mcp-gateway-rules.json to see the watcher in action.
Press Ctrl+C to stop.
"""

import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_watcher import ConfigWatcher

# Configure logging to see debug output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def on_mcp_config_changed(config_path: str) -> None:
    """Called when MCP server configuration changes."""
    logger.info(f"MCP CONFIG CHANGED: {config_path}")
    logger.info("In a real application, you would reload the MCP server config here")


def on_gateway_rules_changed(rules_path: str) -> None:
    """Called when gateway rules configuration changes."""
    logger.info(f"GATEWAY RULES CHANGED: {rules_path}")
    logger.info("In a real application, you would reload the gateway rules here")


def main():
    """Run the config watcher demo."""
    # Get config paths (adjust these to your actual paths)
    project_root = Path(__file__).parent.parent
    mcp_config = project_root / "examples" / "config" / ".mcp.json"
    gateway_rules = project_root / "examples" / "config" / ".mcp-gateway-rules.json"

    # Check if files exist
    if not mcp_config.exists():
        logger.error(f"MCP config not found: {mcp_config}")
        logger.info("Please create the example config files or adjust paths")
        return 1

    if not gateway_rules.exists():
        logger.error(f"Gateway rules not found: {gateway_rules}")
        logger.info("Please create the example config files or adjust paths")
        return 1

    logger.info("=" * 60)
    logger.info("ConfigWatcher Demo")
    logger.info("=" * 60)
    logger.info(f"Watching MCP config: {mcp_config}")
    logger.info(f"Watching gateway rules: {gateway_rules}")
    logger.info("")
    logger.info("Try modifying the config files to see the watcher in action!")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    logger.info("")

    # Create and start watcher
    watcher = ConfigWatcher(
        mcp_config_path=str(mcp_config.resolve()),
        gateway_rules_path=str(gateway_rules.resolve()),
        on_mcp_config_changed=on_mcp_config_changed,
        on_gateway_rules_changed=on_gateway_rules_changed,
        debounce_seconds=0.3,
    )

    try:
        watcher.start()

        # Keep running until interrupted
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\nShutting down watcher...")
        watcher.stop()
        logger.info("Demo complete!")
        return 0
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        watcher.stop()
        return 1


if __name__ == "__main__":
    sys.exit(main())
