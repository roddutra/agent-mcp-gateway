#!/usr/bin/env python3
"""Demonstration of PolicyEngine reload functionality.

This script shows how to use the PolicyEngine.reload() method to update
agent access rules at runtime without restarting the application.
"""

import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.policy import PolicyEngine

# Configure logging to see reload messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    print("=" * 70)
    print("PolicyEngine Reload Demonstration")
    print("=" * 70)
    print()

    # Initial rules configuration
    initial_rules = {
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
                    "tools": {"postgres": ["query", "read_*"]}
                },
                "deny": {
                    "tools": {"postgres": ["drop_*", "delete_*"]}
                }
            }
        },
        "defaults": {"deny_on_missing_agent": True}
    }

    print("1. Creating PolicyEngine with initial rules...")
    print()
    engine = PolicyEngine(initial_rules)

    # Test initial permissions
    print("Initial Permissions:")
    print(f"  - researcher can access brave-search: {engine.can_access_server('researcher', 'brave-search')}")
    print(f"  - researcher can access postgres: {engine.can_access_server('researcher', 'postgres')}")
    print(f"  - backend can execute postgres.query: {engine.can_access_tool('backend', 'postgres', 'query')}")
    print(f"  - backend can execute postgres.drop_table: {engine.can_access_tool('backend', 'postgres', 'drop_table')}")
    print(f"  - unknown agent can access any server: {engine.can_access_server('unknown', 'postgres')}")
    print()

    # Updated rules - add new agent, modify existing, change defaults
    print("2. Reloading with updated rules...")
    print()
    updated_rules = {
        "agents": {
            "researcher": {
                "allow": {
                    "servers": ["brave-search", "postgres"],  # Added postgres
                    "tools": {
                        "brave-search": ["*"],
                        "postgres": ["read_*", "list_*"]  # Read-only access
                    }
                }
            },
            "backend": {
                "allow": {
                    "servers": ["postgres"],
                    "tools": {"postgres": ["*"]}  # Full access now
                },
                "deny": {
                    "tools": {"postgres": ["drop_*"]}  # Still deny dangerous ops
                }
            },
            "data-scientist": {  # New agent
                "allow": {
                    "servers": ["postgres"],
                    "tools": {"postgres": ["query", "read_*"]}
                }
            }
        },
        "defaults": {"deny_on_missing_agent": False}  # Changed to permissive
    }

    success, error = engine.reload(updated_rules)

    if success:
        print("\nReload successful!")
    else:
        print(f"\nReload failed: {error}")
        return

    print()

    # Test updated permissions
    print("Updated Permissions:")
    print(f"  - researcher can access postgres: {engine.can_access_server('researcher', 'postgres')}")
    print(f"  - researcher can execute postgres.read_data: {engine.can_access_tool('researcher', 'postgres', 'read_data')}")
    print(f"  - backend can execute postgres.delete_user: {engine.can_access_tool('backend', 'postgres', 'delete_user')}")
    print(f"  - backend can execute postgres.drop_table: {engine.can_access_tool('backend', 'postgres', 'drop_table')}")
    print(f"  - data-scientist can access postgres: {engine.can_access_server('data-scientist', 'postgres')}")
    print(f"  - unknown agent can access any server: {engine.can_access_server('unknown', 'postgres')}")
    print()

    # Demonstrate validation failure
    print("3. Attempting reload with invalid rules...")
    print()
    invalid_rules = {
        "agents": {
            "bad-agent": {
                "allow": {
                    "servers": "not-a-list",  # Should be a list
                    "tools": {}
                }
            }
        }
    }

    success, error = engine.reload(invalid_rules)

    if not success:
        print(f"Reload correctly rejected: {error}")
    else:
        print("ERROR: Invalid rules were accepted!")

    print()

    # Verify rules didn't change after failed reload
    print("Verifying rules unchanged after failed reload:")
    print(f"  - researcher can still access postgres: {engine.can_access_server('researcher', 'postgres')}")
    print(f"  - data-scientist still exists: {engine.can_access_server('data-scientist', 'postgres')}")
    print()

    print("=" * 70)
    print("Demonstration Complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
