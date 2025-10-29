"""End-to-end tests for hot reload functionality.

This module contains comprehensive integration tests that verify the complete
hot reload flow from file modification to policy evaluation. These tests verify
that the three recent fixes work together correctly:

1. Validation Fix: Rules can reference undefined servers (warnings, not errors)
2. Thread Safety: PolicyEngine operations are thread-safe with RLock
3. Error Visibility: Hot reload status tracking and diagnostic tool
"""

import asyncio
import json
import logging
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.config import (
    reload_configs,
    get_last_validation_warnings,
)
from src.config_watcher import ConfigWatcher
from src.gateway import initialize_gateway
from src.policy import PolicyEngine

# Import the gateway module to access tool implementations
import src.gateway as gateway_module

# Helper to get the underlying function from FastMCP tool
def get_tool_fn(tool):
    """Extract the underlying function from a FastMCP FunctionTool."""
    return tool.fn if hasattr(tool, 'fn') else tool

logger = logging.getLogger(__name__)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for test config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mcp_config_with_brave_only():
    """MCP config with only brave-search server."""
    return {
        "mcpServers": {
            "brave-search": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"]
            }
        }
    }


@pytest.fixture
def gateway_rules_with_postgres():
    """Gateway rules referencing postgres server (not in mcp_config_with_brave_only)."""
    return {
        "agents": {
            "backend": {
                "allow": {
                    "servers": ["postgres"],
                    "tools": {"postgres": ["query", "list_*"]}
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": True
        }
    }


@pytest.fixture
def valid_gateway_rules():
    """Valid gateway rules that match brave-search server."""
    return {
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
    }


def write_config_file(path: Path, config: dict):
    """Helper to write a config file atomically (like editors do).

    Many editors use atomic writes: write to temp file, then rename.
    This simulates that behavior.
    """
    # Write to a temp file first
    temp_path = Path(f"{path}.tmp")
    with open(temp_path, "w") as f:
        json.dump(config, f, indent=2)

    # Atomic rename
    temp_path.replace(path)


# ============================================================================
# Test Scenario 1: Reload with Undefined Servers
# ============================================================================


class TestReloadWithUndefinedServers:
    """Test that hot reload succeeds when rules reference servers not in mcp-servers.json."""

    def test_reload_configs_with_undefined_servers_succeeds(
        self, temp_config_dir, mcp_config_with_brave_only, gateway_rules_with_postgres
    ):
        """Test that reload_configs() succeeds when rules reference undefined servers.

        Flow:
        1. Create temp configs (mcp-servers.json with only brave-search)
        2. Create rules that reference postgres (undefined server)
        3. Call reload_configs()
        4. Assert reload succeeds (returns configs, no error)
        5. Verify warnings were generated and stored
        """
        # Create config files
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        write_config_file(mcp_path, mcp_config_with_brave_only)
        write_config_file(rules_path, gateway_rules_with_postgres)

        # Reload configs
        mcp_config, gateway_rules, error = reload_configs(str(mcp_path), str(rules_path))

        # Assert reload succeeded
        assert mcp_config is not None, "MCP config should be loaded"
        assert gateway_rules is not None, "Gateway rules should be loaded"
        assert error is None, f"Reload should succeed, but got error: {error}"

        # Verify warnings were generated
        warnings = get_last_validation_warnings()
        assert len(warnings) > 0, "Should have warnings about undefined server"
        assert any("postgres" in w for w in warnings), "Warnings should mention postgres"

    def test_policy_engine_reload_with_undefined_servers(
        self, temp_config_dir, mcp_config_with_brave_only, gateway_rules_with_postgres
    ):
        """Test that PolicyEngine reload succeeds with undefined server warnings.

        Flow:
        1. Initialize PolicyEngine with valid rules
        2. Reload with rules referencing undefined servers
        3. Verify reload succeeds
        4. Verify PolicyEngine can still evaluate policies
        """
        # Create initial valid rules
        initial_rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["brave-search"],
                        "tools": {"brave-search": ["*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(initial_rules)

        # Verify initial state
        assert engine.can_access_server("test", "brave-search") is True

        # Reload with rules referencing undefined server
        success, error = engine.reload(gateway_rules_with_postgres)

        # Assert reload succeeded
        assert success is True, f"Reload should succeed, but got error: {error}"
        assert error is None

        # Verify PolicyEngine still works (can evaluate policies)
        # The new agent "backend" should be loaded
        assert "backend" in engine.agents
        # But it won't have access to postgres since it's not a configured server
        # (policy engine doesn't validate against server existence)
        assert engine.can_access_server("backend", "postgres") is True


# ============================================================================
# Test Scenario 2: Hot Reload Flow Simulation
# ============================================================================


class TestHotReloadFlowSimulation:
    """Test the complete flow from file change detection to policy update."""

    @pytest.mark.asyncio
    async def test_complete_hot_reload_flow(
        self, temp_config_dir, mcp_config_with_brave_only, valid_gateway_rules
    ):
        """Test complete flow: File change -> Callback -> Reload -> New policy active.

        Flow:
        1. Create temporary config files
        2. Initialize ConfigWatcher with callbacks
        3. Start the watcher
        4. Modify gateway-rules.json file (add a deny rule)
        5. Wait for debounce period
        6. Verify callback was triggered
        7. Verify PolicyEngine was reloaded
        8. Verify new deny rule is enforced
        """
        # Create config files
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        write_config_file(mcp_path, mcp_config_with_brave_only)
        write_config_file(rules_path, valid_gateway_rules)

        # Initialize PolicyEngine with initial rules
        engine = PolicyEngine(valid_gateway_rules)

        # Verify initial state - researcher can use all tools
        assert engine.can_access_tool("researcher", "brave-search", "brave_web_search") is True

        # Track reload events
        reload_called = asyncio.Event()
        reload_successful = False

        def on_rules_changed(rules_config_path: str):
            """Callback that reloads PolicyEngine."""
            nonlocal reload_successful
            logger.info(f"Gateway rules changed: {rules_config_path}")

            # Load and validate new rules
            mcp_config, gateway_rules, error = reload_configs(str(mcp_path), rules_config_path)
            if error:
                logger.error(f"Reload failed: {error}")
                reload_called.set()
                return

            # Reload PolicyEngine
            success, reload_error = engine.reload(gateway_rules)
            reload_successful = success
            if not success:
                logger.error(f"PolicyEngine reload failed: {reload_error}")

            reload_called.set()

        def on_mcp_changed(config_path: str):
            """Dummy callback for MCP config."""
            pass

        # Start watcher
        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_path),
            gateway_rules_path=str(rules_path),
            on_mcp_config_changed=on_mcp_changed,
            on_gateway_rules_changed=on_rules_changed,
            debounce_seconds=0.1
        )
        watcher.start()

        try:
            # Modify gateway rules - add a deny rule
            modified_rules = {
                "agents": {
                    "researcher": {
                        "allow": {
                            "servers": ["brave-search"],
                            "tools": {"brave-search": ["*"]}
                        },
                        "deny": {
                            "tools": {"brave-search": ["brave_local_search"]}  # NEW DENY RULE
                        }
                    }
                },
                "defaults": {
                    "deny_on_missing_agent": True
                }
            }
            write_config_file(rules_path, modified_rules)

            # Wait for reload callback (debounce + processing)
            try:
                await asyncio.wait_for(reload_called.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pytest.fail("Reload callback was not triggered within timeout")

            # Verify reload was successful
            assert reload_successful is True, "PolicyEngine reload should succeed"

            # Verify new deny rule is enforced
            assert engine.can_access_tool("researcher", "brave-search", "brave_web_search") is True
            assert engine.can_access_tool("researcher", "brave-search", "brave_local_search") is False

        finally:
            watcher.stop()


# ============================================================================
# Test Scenario 3: get_last_validation_warnings()
# ============================================================================


class TestGetLastValidationWarnings:
    """Test the diagnostic function returns correct warnings."""

    def test_warnings_tracked_after_reload(
        self, temp_config_dir, mcp_config_with_brave_only, gateway_rules_with_postgres
    ):
        """Test that warnings are tracked after reload with undefined servers.

        Flow:
        1. Load configs with undefined servers
        2. Call reload_configs()
        3. Call get_last_validation_warnings()
        4. Assert warnings list contains expected messages
        """
        # Create config files
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        write_config_file(mcp_path, mcp_config_with_brave_only)
        write_config_file(rules_path, gateway_rules_with_postgres)

        # Reload configs
        mcp_config, gateway_rules, error = reload_configs(str(mcp_path), str(rules_path))

        # Verify reload succeeded
        assert error is None

        # Get warnings
        warnings = get_last_validation_warnings()

        # Assert warnings contain expected messages
        assert len(warnings) > 0, "Should have warnings"
        assert any("postgres" in w for w in warnings), "Should warn about postgres"
        assert any("backend" in w for w in warnings), "Should mention agent backend"

    def test_warnings_cleared_after_valid_reload(
        self, temp_config_dir, mcp_config_with_brave_only, valid_gateway_rules
    ):
        """Test that warnings are cleared after reload with valid configs.

        Flow:
        1. First reload with undefined servers (generates warnings)
        2. Second reload with valid configs
        3. Assert warnings list is empty
        """
        # Create config files
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        # First reload with undefined servers
        invalid_rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["nonexistent"],
                        "tools": {"nonexistent": ["*"]}
                    }
                }
            }
        }

        write_config_file(mcp_path, mcp_config_with_brave_only)
        write_config_file(rules_path, invalid_rules)

        reload_configs(str(mcp_path), str(rules_path))

        # Verify warnings exist
        warnings = get_last_validation_warnings()
        assert len(warnings) > 0

        # Second reload with valid configs
        write_config_file(rules_path, valid_gateway_rules)
        reload_configs(str(mcp_path), str(rules_path))

        # Assert warnings are cleared
        warnings = get_last_validation_warnings()
        assert len(warnings) == 0, "Warnings should be cleared after valid reload"


# ============================================================================
# Test Scenario 4: Thread Safety During Reload
# ============================================================================


class TestThreadSafetyDuringReload:
    """Test PolicyEngine can handle concurrent reads during reload."""

    def test_concurrent_access_during_reload(self):
        """Test PolicyEngine handles concurrent reads during reload.

        Flow:
        1. Initialize PolicyEngine with rules
        2. Start background thread that continuously calls can_access_tool()
        3. In main thread, repeatedly call reload() with new rules
        4. Let both threads run for 1 second
        5. Verify no exceptions occurred
        6. Verify policy evaluations are consistent
        """
        # Initialize with rules
        initial_rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["get_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(initial_rules)

        # Track errors and results
        errors = []
        access_results = []
        stop_flag = threading.Event()

        def continuous_access_checks():
            """Background thread that continuously checks access."""
            try:
                while not stop_flag.is_set():
                    # Perform access check
                    result = engine.can_access_tool("test", "api", "get_user")
                    access_results.append(result)
                    time.sleep(0.01)  # Small delay
            except Exception as e:
                errors.append(f"Access check error: {e}")

        # Start background thread
        access_thread = threading.Thread(target=continuous_access_checks, daemon=True)
        access_thread.start()

        try:
            # Repeatedly reload rules in main thread
            for i in range(10):
                new_rules = {
                    "agents": {
                        "test": {
                            "allow": {
                                "servers": ["api"],
                                "tools": {"api": ["get_*", f"method_{i}"]}
                            }
                        }
                    }
                }

                success, error = engine.reload(new_rules)
                if not success:
                    errors.append(f"Reload {i} failed: {error}")

                time.sleep(0.05)  # Let access thread run

            # Let threads run a bit more
            time.sleep(0.2)

        finally:
            # Stop background thread
            stop_flag.set()
            access_thread.join(timeout=1.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred during concurrent operations: {errors}"

        # Verify we got consistent results (all should be True since get_* is allowed)
        assert len(access_results) > 0, "Should have collected access results"
        assert all(result is True for result in access_results), \
            "All access checks should succeed (get_user matches get_*)"

    def test_concurrent_reloads_are_safe(self):
        """Test that concurrent reload attempts don't cause race conditions.

        Flow:
        1. Initialize PolicyEngine
        2. Start multiple threads that all try to reload simultaneously
        3. Verify all reloads complete without exceptions
        4. Verify final state is consistent
        """
        initial_rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["api"]}
                }
            }
        }

        engine = PolicyEngine(initial_rules)

        errors = []
        reload_results = []

        def reload_attempt(thread_id: int):
            """Attempt to reload rules."""
            try:
                new_rules = {
                    "agents": {
                        f"agent_{thread_id}": {
                            "allow": {"servers": ["api"]}
                        }
                    }
                }

                success, error = engine.reload(new_rules)
                reload_results.append((thread_id, success, error))
            except Exception as e:
                errors.append(f"Thread {thread_id} error: {e}")

        # Start multiple reload threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=reload_attempt, args=(i,), daemon=True)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=2.0)

        # Verify no exceptions
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all reloads completed
        assert len(reload_results) == 5, "All reload attempts should complete"

        # Verify at least some succeeded (race conditions might cause some to fail validation)
        successful_reloads = [r for r in reload_results if r[1] is True]
        assert len(successful_reloads) > 0, "At least one reload should succeed"

        # Verify final state is consistent (one of the agents should exist)
        assert len(engine.agents) > 0, "Should have at least one agent loaded"


# ============================================================================
# Test Scenario 5: get_gateway_status Tool
# ============================================================================


class TestGetGatewayStatusTool:
    """Test the diagnostic tool returns comprehensive status."""

    @pytest.mark.asyncio
    async def test_gateway_status_returns_comprehensive_info(
        self, temp_config_dir, mcp_config_with_brave_only, valid_gateway_rules
    ):
        """Test that get_gateway_status() returns accurate status.

        Flow:
        1. Initialize gateway with all components
        2. Call get_gateway_status(agent_id="test")
        3. Assert response contains expected fields
        """
        # Create config files
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        write_config_file(mcp_path, mcp_config_with_brave_only)
        write_config_file(rules_path, valid_gateway_rules)

        # Load configs
        from src.config import load_mcp_config, load_gateway_rules
        mcp_config = load_mcp_config(str(mcp_path))
        gateway_rules = load_gateway_rules(str(rules_path))

        # Initialize PolicyEngine
        engine = PolicyEngine(gateway_rules)

        # Mock reload status function
        from datetime import datetime

        def mock_get_reload_status():
            return {
                "mcp_config": {
                    "last_attempt": datetime.fromisoformat("2025-01-15T10:30:00"),
                    "last_success": datetime.fromisoformat("2025-01-15T10:30:00"),
                    "last_error": None,
                    "attempt_count": 1,
                    "success_count": 1
                },
                "gateway_rules": {
                    "last_attempt": datetime.fromisoformat("2025-01-15T10:35:00"),
                    "last_success": datetime.fromisoformat("2025-01-15T10:35:00"),
                    "last_error": None,
                    "attempt_count": 1,
                    "success_count": 1,
                    "last_warnings": []
                }
            }

        # Initialize gateway
        initialize_gateway(
            policy_engine=engine,
            mcp_config=mcp_config,
            proxy_manager=None,  # Not needed for this test
            check_config_changes_fn=None,
            get_reload_status_fn=mock_get_reload_status
        )

        # Call get_gateway_status
        get_status_fn = get_tool_fn(gateway_module.get_gateway_status)
        status = await get_status_fn(agent_id="test")

        # Assert response structure
        assert "reload_status" in status
        assert "policy_state" in status
        assert "available_servers" in status
        assert "config_paths" in status
        assert "message" in status

        # Verify reload_status
        assert status["reload_status"] is not None
        assert "mcp_config" in status["reload_status"]
        assert "gateway_rules" in status["reload_status"]

        # Verify policy_state
        assert status["policy_state"]["total_agents"] == 1
        assert "researcher" in status["policy_state"]["agent_ids"]
        assert status["policy_state"]["defaults"]["deny_on_missing_agent"] is True

        # Verify available_servers
        assert status["available_servers"] == ["brave-search"]

        # Verify config_paths
        assert "mcp_config" in status["config_paths"]
        assert "gateway_rules" in status["config_paths"]

    @pytest.mark.asyncio
    async def test_gateway_status_after_reload(
        self, temp_config_dir, mcp_config_with_brave_only, valid_gateway_rules
    ):
        """Test that get_gateway_status() reflects updated state after reload.

        Flow:
        1. Initialize gateway
        2. Call get_gateway_status() - capture initial state
        3. Trigger a reload (add new agent)
        4. Call get_gateway_status() again
        5. Verify agent count increased
        """
        # Create config files
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        write_config_file(mcp_path, mcp_config_with_brave_only)
        write_config_file(rules_path, valid_gateway_rules)

        # Load configs
        from src.config import load_mcp_config, load_gateway_rules
        mcp_config = load_mcp_config(str(mcp_path))
        gateway_rules = load_gateway_rules(str(rules_path))

        # Initialize PolicyEngine
        engine = PolicyEngine(gateway_rules)

        # Initialize gateway
        initialize_gateway(
            policy_engine=engine,
            mcp_config=mcp_config,
            proxy_manager=None,
            check_config_changes_fn=None,
            get_reload_status_fn=None
        )

        # Get initial status
        get_status_fn = get_tool_fn(gateway_module.get_gateway_status)
        initial_status = await get_status_fn(agent_id="test")
        initial_agent_count = initial_status["policy_state"]["total_agents"]
        assert initial_agent_count == 1

        # Reload with additional agent
        modified_rules = {
            "agents": {
                "researcher": {
                    "allow": {
                        "servers": ["brave-search"],
                        "tools": {"brave-search": ["*"]}
                    }
                },
                "backend": {
                    "allow": {
                        "servers": ["brave-search"],
                        "tools": {"brave-search": ["brave_web_search"]}
                    }
                }
            },
            "defaults": {
                "deny_on_missing_agent": True
            }
        }

        success, error = engine.reload(modified_rules)
        assert success is True

        # Get updated status
        updated_status = await get_status_fn(agent_id="test")
        updated_agent_count = updated_status["policy_state"]["total_agents"]

        # Verify agent count increased
        assert updated_agent_count == 2
        assert "backend" in updated_status["policy_state"]["agent_ids"]


# ============================================================================
# Test Scenario 6: Integration Test - All Fixes Working Together
# ============================================================================


class TestAllFixesWorkingTogether:
    """Test that all three fixes work together in realistic scenarios."""

    @pytest.mark.asyncio
    async def test_complete_hot_reload_with_warnings_and_thread_safety(
        self, temp_config_dir
    ):
        """Test complete hot reload with undefined servers, thread safety, and status tracking.

        This test combines all three fixes:
        1. Rules can reference undefined servers (warnings, not errors)
        2. PolicyEngine is thread-safe during concurrent access
        3. Status tracking provides visibility into reload health

        Flow:
        1. Start with configs where rules reference undefined server
        2. Start background thread doing continuous policy checks
        3. Trigger file change to reload configs
        4. Verify reload succeeds with warnings
        5. Verify no thread safety issues
        6. Verify get_gateway_status shows correct state
        """
        # Create config files
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        # Initial MCP config (only brave-search)
        mcp_config = {
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-brave-search"]
                }
            }
        }

        # Initial rules (references both brave-search and postgres)
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
                        "servers": ["postgres"],  # Undefined server!
                        "tools": {"postgres": ["query"]}
                    }
                }
            },
            "defaults": {
                "deny_on_missing_agent": True
            }
        }

        write_config_file(mcp_path, mcp_config)
        write_config_file(rules_path, initial_rules)

        # Load and verify initial configs succeed despite undefined server
        from src.config import load_mcp_config, load_gateway_rules
        loaded_mcp_config = load_mcp_config(str(mcp_path))
        loaded_rules = load_gateway_rules(str(rules_path))

        # Reload configs to generate warnings
        reload_mcp, reload_rules, error = reload_configs(str(mcp_path), str(rules_path))
        assert error is None, "Reload should succeed despite undefined server"
        assert reload_mcp is not None
        assert reload_rules is not None

        # Verify warnings were generated
        warnings = get_last_validation_warnings()
        assert len(warnings) > 0
        assert any("postgres" in w for w in warnings)

        # Initialize PolicyEngine
        engine = PolicyEngine(loaded_rules)

        # Track thread safety
        errors = []
        stop_flag = threading.Event()

        def continuous_checks():
            """Background thread doing continuous policy checks."""
            try:
                while not stop_flag.is_set():
                    # Check various policies
                    engine.can_access_server("researcher", "brave-search")
                    engine.can_access_tool("researcher", "brave-search", "brave_web_search")
                    engine.get_allowed_servers("researcher")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"Thread safety error: {e}")

        # Start background thread
        check_thread = threading.Thread(target=continuous_checks, daemon=True)
        check_thread.start()

        try:
            # Initialize gateway with mock reload status
            from datetime import datetime

            reload_status_calls = []

            def mock_get_reload_status():
                reload_status_calls.append(time.time())
                return {
                    "mcp_config": {
                        "last_attempt": datetime.fromisoformat("2025-01-15T10:30:00"),
                        "last_success": datetime.fromisoformat("2025-01-15T10:30:00"),
                        "last_error": None,
                        "attempt_count": 1,
                        "success_count": 1
                    },
                    "gateway_rules": {
                        "last_attempt": datetime.fromisoformat("2025-01-15T10:35:00"),
                        "last_success": datetime.fromisoformat("2025-01-15T10:35:00"),
                        "last_error": None,
                        "attempt_count": 1,
                        "success_count": 1,
                        "last_warnings": get_last_validation_warnings()
                    }
                }

            initialize_gateway(
                policy_engine=engine,
                mcp_config=loaded_mcp_config,
                proxy_manager=None,
                check_config_changes_fn=None,
                get_reload_status_fn=mock_get_reload_status
            )

            # Trigger multiple reloads while background thread is running
            for i in range(3):
                new_rules = {
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
                                "tools": {"postgres": ["query", f"method_{i}"]}
                            }
                        }
                    },
                    "defaults": {
                        "deny_on_missing_agent": True
                    }
                }

                success, reload_error = engine.reload(new_rules)
                assert success is True, f"Reload {i} should succeed"

                # Small delay between reloads
                time.sleep(0.1)

            # Check gateway status
            get_status_fn = get_tool_fn(gateway_module.get_gateway_status)
            status = await get_status_fn(agent_id="researcher")

            # Verify status includes warnings
            assert status["reload_status"] is not None
            assert "gateway_rules" in status["reload_status"]
            warnings_in_status = status["reload_status"]["gateway_rules"]["last_warnings"]
            assert len(warnings_in_status) > 0
            assert any("postgres" in w for w in warnings_in_status)

            # Verify policy state
            assert status["policy_state"]["total_agents"] == 2
            assert set(status["policy_state"]["agent_ids"]) == {"researcher", "backend"}

        finally:
            # Stop background thread
            stop_flag.set()
            check_thread.join(timeout=1.0)

        # Verify no thread safety errors
        assert len(errors) == 0, f"Thread safety errors occurred: {errors}"


# ============================================================================
# Test Scenario 7: Validation Warnings Content
# ============================================================================


class TestValidationWarningsContent:
    """Test that validation warnings contain accurate and helpful information."""

    def test_warnings_include_agent_and_server_details(
        self, temp_config_dir
    ):
        """Test that warnings include both agent name and server name.

        Flow:
        1. Create rules with multiple agents referencing undefined servers
        2. Reload configs
        3. Verify warnings mention specific agents and servers
        """
        # Create configs
        mcp_path = temp_config_dir / "mcp-servers.json"
        rules_path = temp_config_dir / "gateway-rules.json"

        mcp_config = {
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["-y", "test"]
                }
            }
        }

        rules = {
            "agents": {
                "agent1": {
                    "allow": {
                        "servers": ["undefined_server_1"],
                        "tools": {"undefined_server_1": ["*"]}
                    }
                },
                "agent2": {
                    "allow": {
                        "servers": ["undefined_server_2"],
                        "tools": {"undefined_server_2": ["query"]}
                    }
                }
            }
        }

        write_config_file(mcp_path, mcp_config)
        write_config_file(rules_path, rules)

        # Reload configs
        reload_configs(str(mcp_path), str(rules_path))

        # Get warnings
        warnings = get_last_validation_warnings()

        # Verify warnings mention agent1 and undefined_server_1
        assert any("agent1" in w and "undefined_server_1" in w for w in warnings)

        # Verify warnings mention agent2 and undefined_server_2
        assert any("agent2" in w and "undefined_server_2" in w for w in warnings)
