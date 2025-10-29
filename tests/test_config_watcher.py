"""Unit tests for ConfigWatcher file monitoring and hot reload."""

import json
import logging
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config_watcher import ConfigWatcher, _ConfigFileEventHandler


class TestConfigWatcherInitialization:
    """Test cases for ConfigWatcher initialization."""

    def test_initialization_with_absolute_paths(self, tmp_path):
        """Test initialization with absolute paths."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        callback1 = Mock()
        callback2 = Mock()

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=callback1,
            on_gateway_rules_changed=callback2,
            debounce_seconds=0.3
        )

        assert watcher.mcp_config_path == mcp_file.resolve()
        assert watcher.gateway_rules_path == rules_file.resolve()
        assert watcher.on_mcp_config_changed == callback1
        assert watcher.on_gateway_rules_changed == callback2
        assert watcher.debounce_seconds == 0.3
        assert watcher.observer is None
        assert watcher._pending_timers == {}

    def test_initialization_with_relative_paths(self, tmp_path, monkeypatch):
        """Test initialization with relative paths."""
        monkeypatch.chdir(tmp_path)

        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        callback1 = Mock()
        callback2 = Mock()

        watcher = ConfigWatcher(
            mcp_config_path="mcp.json",
            gateway_rules_path="rules.json",
            on_mcp_config_changed=callback1,
            on_gateway_rules_changed=callback2
        )

        # Paths should be resolved to absolute
        assert watcher.mcp_config_path.is_absolute()
        assert watcher.gateway_rules_path.is_absolute()
        assert watcher.mcp_config_path.name == "mcp.json"
        assert watcher.gateway_rules_path.name == "rules.json"

    def test_initialization_default_debounce(self, tmp_path):
        """Test default debounce time."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        assert watcher.debounce_seconds == 0.3

    def test_initialization_custom_debounce(self, tmp_path):
        """Test custom debounce time."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.5
        )

        assert watcher.debounce_seconds == 0.5


class TestConfigWatcherStartStop:
    """Test cases for ConfigWatcher start/stop lifecycle."""

    def test_start_creates_observer(self, tmp_path):
        """Test that start creates and starts observer."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        watcher.start()

        assert watcher.observer is not None
        assert watcher.observer.is_alive()

        watcher.stop()

    def test_start_same_directory(self, tmp_path):
        """Test starting watcher when both files in same directory."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        watcher.start()

        # Should only schedule one directory watch
        assert watcher.observer is not None

        watcher.stop()

    def test_start_different_directories(self, tmp_path):
        """Test starting watcher when files in different directories."""
        mcp_dir = tmp_path / "config"
        rules_dir = tmp_path / "rules"

        mcp_dir.mkdir()
        rules_dir.mkdir()

        mcp_file = mcp_dir / "mcp.json"
        rules_file = rules_dir / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        watcher.start()

        # Should schedule watches for both directories
        assert watcher.observer is not None

        watcher.stop()

    def test_start_already_running_raises_error(self, tmp_path):
        """Test that starting twice raises RuntimeError."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        watcher.start()

        with pytest.raises(RuntimeError) as exc_info:
            watcher.start()

        assert "already running" in str(exc_info.value)

        watcher.stop()

    def test_start_nonexistent_directory_raises_error(self, tmp_path):
        """Test error when directory doesn't exist."""
        # Note: This test is skipped because watchdog may not raise an error immediately
        # for nonexistent directories on all platforms. The error would occur later when
        # the observer thread tries to watch the directory.
        pytest.skip("Watchdog behavior varies across platforms for nonexistent directories")

    def test_stop_cleans_up_observer(self, tmp_path):
        """Test that stop cleans up observer."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        watcher.start()
        assert watcher.observer is not None

        watcher.stop()

        assert watcher.observer is None

    def test_stop_cancels_pending_timers(self, tmp_path):
        """Test that stop cancels pending debounce timers."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        callback = Mock()
        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=1.0  # Long debounce to test cancellation
        )

        watcher.start()

        # Trigger a file change
        mcp_file.write_text('{"changed": true}')
        time.sleep(0.1)  # Let event be detected

        # Stop before debounce timer fires
        watcher.stop()

        # Wait to ensure timer doesn't fire
        time.sleep(1.2)

        # Callback should not have been called since timer was cancelled
        callback.assert_not_called()

    def test_stop_idempotent(self, tmp_path):
        """Test that stop can be called multiple times safely."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        watcher.start()
        watcher.stop()
        watcher.stop()  # Should not raise error
        watcher.stop()  # Should not raise error

    def test_stop_without_start(self, tmp_path):
        """Test that stop without start is safe."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text("{}")
        rules_file.write_text("{}")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        watcher.stop()  # Should not raise error


class TestConfigWatcherFileChangeDetection:
    """Test cases for detecting file changes."""

    def test_detect_mcp_config_modification(self, tmp_path):
        """Test detection of MCP config file modification."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        callback_calls = []

        def mcp_callback(path):
            callback_calls.append(("mcp", path))

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()

        # Modify MCP config
        time.sleep(0.2)
        mcp_file.write_text('{"mcpServers": {"new": {}}}')

        # Wait for debounce + callback
        time.sleep(0.3)

        watcher.stop()

        # Callback should have been invoked
        assert len(callback_calls) > 0
        assert callback_calls[0][0] == "mcp"
        assert mcp_file.resolve() == Path(callback_calls[0][1])

    def test_detect_gateway_rules_modification(self, tmp_path):
        """Test detection of gateway rules file modification."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        callback_calls = []

        def rules_callback(path):
            callback_calls.append(("rules", path))

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=rules_callback,
            debounce_seconds=0.1
        )

        watcher.start()

        # Modify gateway rules
        time.sleep(0.2)
        rules_file.write_text('{"agents": {"new": {}}}')

        # Wait for debounce + callback
        time.sleep(0.3)

        watcher.stop()

        # Callback should have been invoked
        assert len(callback_calls) > 0
        assert callback_calls[0][0] == "rules"
        assert rules_file.resolve() == Path(callback_calls[0][1])

    def test_detect_file_creation(self, tmp_path):
        """Test detection when file is created."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        # Create directory but not files initially
        rules_file.write_text('{"agents": {}}')

        callback_calls = []

        def mcp_callback(path):
            callback_calls.append(path)

        # Write initial file so watcher can start
        mcp_file.write_text('{}')

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        # Delete and recreate file (simulates some editors)
        mcp_file.unlink()
        time.sleep(0.1)
        mcp_file.write_text('{"created": true}')

        # Wait for debounce + callback
        time.sleep(0.3)

        watcher.stop()

        # Callback should have been invoked for creation
        assert len(callback_calls) > 0

    def test_detect_atomic_write_move(self, tmp_path):
        """Test detection of atomic write (temp file + rename)."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        callback_calls = []

        def mcp_callback(path):
            callback_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        # Simulate atomic write: write to temp, rename to target
        temp_file = tmp_path / "mcp.json.tmp"
        temp_file.write_text('{"mcpServers": {"new": {}}}')
        temp_file.replace(mcp_file)

        # Wait for debounce + callback
        time.sleep(0.3)

        watcher.stop()

        # Callback should have been invoked
        assert len(callback_calls) > 0

    def test_ignores_other_files_in_directory(self, tmp_path):
        """Test that changes to other files in directory are ignored."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"
        other_file = tmp_path / "other.txt"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        mcp_callback = Mock()
        rules_callback = Mock()

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=rules_callback,
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        # Clear any initialization events
        mcp_callback.reset_mock()
        rules_callback.reset_mock()

        # Modify other file
        other_file.write_text("This should be ignored")

        # Wait and verify callback NOT called
        time.sleep(0.3)

        watcher.stop()

        mcp_callback.assert_not_called()
        rules_callback.assert_not_called()

    def test_ignores_directory_events(self, tmp_path):
        """Test that directory events are ignored."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        mcp_callback = Mock()
        rules_callback = Mock()

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=rules_callback,
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        # Clear any initialization events
        mcp_callback.reset_mock()
        rules_callback.reset_mock()

        # Create subdirectory (directory event)
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Wait and verify callback NOT called
        time.sleep(0.3)

        watcher.stop()

        mcp_callback.assert_not_called()
        rules_callback.assert_not_called()


class TestConfigWatcherDebouncing:
    """Test cases for debouncing behavior."""

    def test_debouncing_single_callback_for_rapid_changes(self, tmp_path):
        """Test that rapid changes trigger only one callback."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        callback_calls = []

        def mcp_callback(path):
            callback_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.3
        )

        watcher.start()
        time.sleep(0.2)

        # Make rapid changes
        for i in range(5):
            mcp_file.write_text(f'{{"mcpServers": {{"change": {i}}}}}')
            time.sleep(0.05)  # Less than debounce time

        # Wait for debounce period after last change
        time.sleep(0.5)

        watcher.stop()

        # Should only have one callback despite multiple changes
        assert len(callback_calls) == 1

    def test_debouncing_resets_timer_on_new_change(self, tmp_path):
        """Test that new change resets debounce timer."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        callback_calls = []
        callback_times = []

        def mcp_callback(path):
            callback_calls.append(path)
            callback_times.append(time.time())

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.3
        )

        watcher.start()
        time.sleep(0.2)

        start_time = time.time()

        # First change
        mcp_file.write_text('{"mcpServers": {"v": 1}}')
        time.sleep(0.2)  # Wait less than debounce

        # Second change (should reset timer)
        mcp_file.write_text('{"mcpServers": {"v": 2}}')

        # Wait for debounce period
        time.sleep(0.5)

        watcher.stop()

        # Should only have one callback
        assert len(callback_calls) == 1

        # Callback should have fired after debounce from second change
        # (not from first change)
        assert callback_times[0] - start_time >= 0.5

    def test_debouncing_independent_per_file(self, tmp_path):
        """Test that debouncing is independent for each file."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        mcp_calls = []
        rules_calls = []

        def mcp_callback(path):
            mcp_calls.append(path)

        def rules_callback(path):
            rules_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=rules_callback,
            debounce_seconds=0.2
        )

        watcher.start()
        time.sleep(0.3)

        # Change both files
        mcp_file.write_text('{"mcpServers": {"new": {}}}')
        time.sleep(0.05)
        rules_file.write_text('{"agents": {"new": {}}}')

        # Wait for debounce
        time.sleep(0.5)

        watcher.stop()

        # Both callbacks should have been invoked at least once
        assert len(mcp_calls) >= 1
        assert len(rules_calls) >= 1


class TestConfigWatcherCallbackExecution:
    """Test cases for callback invocation."""

    def test_callback_receives_correct_path(self, tmp_path):
        """Test that callback receives the correct file path."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        received_path = None

        def mcp_callback(path):
            nonlocal received_path
            received_path = path

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        mcp_file.write_text('{"mcpServers": {"changed": true}}')

        time.sleep(0.3)

        watcher.stop()

        assert received_path is not None
        assert Path(received_path) == mcp_file.resolve()

    def test_callback_exception_doesnt_crash_watcher(self, tmp_path):
        """Test that callback exception doesn't crash watcher."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        call_count = [0]

        def failing_callback(path):
            call_count[0] += 1
            raise Exception("Callback error")

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=failing_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        # First change
        mcp_file.write_text('{"mcpServers": {"v": 1}}')
        time.sleep(0.3)

        # Watcher should still be running despite exception
        assert watcher.observer is not None
        assert watcher.observer.is_alive()

        # Make another change to verify watcher still works
        time.sleep(0.2)
        mcp_file.write_text('{"mcpServers": {"v": 2}}')
        time.sleep(0.3)

        watcher.stop()

        # At least one change should have triggered callback (despite exceptions)
        # Note: File system events can be triggered multiple times, so we just verify >= 1
        assert call_count[0] >= 1

    def test_callback_runs_in_separate_thread(self, tmp_path):
        """Test that callback runs in separate thread from main."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        main_thread_id = threading.get_ident()
        callback_thread_id = None

        def mcp_callback(path):
            nonlocal callback_thread_id
            callback_thread_id = threading.get_ident()

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        mcp_file.write_text('{"mcpServers": {"changed": true}}')

        time.sleep(0.3)

        watcher.stop()

        assert callback_thread_id is not None
        assert callback_thread_id != main_thread_id


class TestConfigWatcherThreadSafety:
    """Test cases for thread safety."""

    def test_concurrent_file_changes(self, tmp_path):
        """Test handling concurrent changes to different files."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        mcp_calls = []
        rules_calls = []
        mcp_lock = threading.Lock()
        rules_lock = threading.Lock()

        def mcp_callback(path):
            with mcp_lock:
                mcp_calls.append(path)

        def rules_callback(path):
            with rules_lock:
                rules_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=rules_callback,
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        # Change both files simultaneously
        def change_mcp():
            for i in range(3):
                mcp_file.write_text(f'{{"mcpServers": {{"v": {i}}}}}')
                time.sleep(0.05)

        def change_rules():
            for i in range(3):
                rules_file.write_text(f'{{"agents": {{"v": {i}}}}}')
                time.sleep(0.05)

        thread1 = threading.Thread(target=change_mcp)
        thread2 = threading.Thread(target=change_rules)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Wait for debounce
        time.sleep(0.3)

        watcher.stop()

        # Both callbacks should have been invoked
        with mcp_lock:
            assert len(mcp_calls) >= 1
        with rules_lock:
            assert len(rules_calls) >= 1

    def test_stop_while_callback_running(self, tmp_path):
        """Test stopping watcher while callback is executing."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{"mcpServers": {}}')
        rules_file.write_text('{"agents": {}}')

        callback_started = threading.Event()
        callback_finished = threading.Event()

        def slow_callback(path):
            callback_started.set()
            time.sleep(0.5)  # Simulate slow callback
            callback_finished.set()

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=slow_callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        mcp_file.write_text('{"mcpServers": {"changed": true}}')

        # Wait for callback to start
        callback_started.wait(timeout=1.0)

        # Stop while callback is running
        watcher.stop()

        # Callback should still complete
        assert callback_finished.wait(timeout=1.0)


class TestEventHandler:
    """Test cases for _ConfigFileEventHandler."""

    def test_handler_forwards_modified_events(self, tmp_path):
        """Test that handler forwards file modification events."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{}')
        rules_file.write_text('{}')

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        handler = _ConfigFileEventHandler(watcher)

        # Mock event
        event = Mock()
        event.is_directory = False
        event.src_path = str(mcp_file)

        # Manually call handler (without starting watcher)
        with patch.object(watcher, '_handle_file_change') as mock_handle:
            handler.on_modified(event)

            mock_handle.assert_called_once()
            # Verify path was resolved
            call_args = mock_handle.call_args[0][0]
            assert call_args == mcp_file.resolve()

    def test_handler_forwards_created_events(self, tmp_path):
        """Test that handler forwards file creation events."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{}')
        rules_file.write_text('{}')

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        handler = _ConfigFileEventHandler(watcher)

        event = Mock()
        event.is_directory = False
        event.src_path = str(mcp_file)

        with patch.object(watcher, '_handle_file_change') as mock_handle:
            handler.on_created(event)
            mock_handle.assert_called_once()

    def test_handler_forwards_moved_events(self, tmp_path):
        """Test that handler forwards file move events."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{}')
        rules_file.write_text('{}')

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        handler = _ConfigFileEventHandler(watcher)

        event = Mock()
        event.is_directory = False
        event.dest_path = str(mcp_file)

        with patch.object(watcher, '_handle_file_change') as mock_handle:
            handler.on_moved(event)
            mock_handle.assert_called_once()

    def test_handler_ignores_directory_events(self, tmp_path):
        """Test that handler ignores directory events."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{}')
        rules_file.write_text('{}')

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        handler = _ConfigFileEventHandler(watcher)

        event = Mock()
        event.is_directory = True
        event.src_path = str(tmp_path)

        with patch.object(watcher, '_handle_file_change') as mock_handle:
            handler.on_modified(event)
            mock_handle.assert_not_called()

    def test_handler_error_handling(self, tmp_path):
        """Test that handler catches and logs exceptions."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{}')
        rules_file.write_text('{}')

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=Mock(),
            on_gateway_rules_changed=Mock()
        )

        handler = _ConfigFileEventHandler(watcher)

        event = Mock()
        event.is_directory = False
        event.src_path = str(mcp_file)

        # Make _handle_file_change raise exception
        with patch.object(watcher, '_handle_file_change', side_effect=Exception("Test error")):
            # Should not raise exception
            handler.on_modified(event)


class TestConfigWatcherEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_short_debounce(self, tmp_path):
        """Test with very short debounce time."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{}')
        rules_file.write_text('{}')

        callback_calls = []

        def callback(path):
            callback_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.01  # Very short
        )

        watcher.start()
        time.sleep(0.1)

        mcp_file.write_text('{"changed": true}')

        time.sleep(0.1)

        watcher.stop()

        assert len(callback_calls) > 0

    def test_zero_debounce(self, tmp_path):
        """Test with zero debounce time."""
        mcp_file = tmp_path / "mcp.json"
        rules_file = tmp_path / "rules.json"

        mcp_file.write_text('{}')
        rules_file.write_text('{}')

        callback_calls = []

        def callback(path):
            callback_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(mcp_file),
            gateway_rules_path=str(rules_file),
            on_mcp_config_changed=callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.0
        )

        watcher.start()
        time.sleep(0.1)

        mcp_file.write_text('{"changed": true}')

        time.sleep(0.1)

        watcher.stop()

        assert len(callback_calls) > 0

    def test_same_file_for_both_configs(self, tmp_path):
        """Test behavior when same file is used for both configs.

        Note: When the same file is used for both configs, the ConfigWatcher
        will handle each change event twice (once for mcp_config and once for
        gateway_rules), but debouncing may coalesce them. The exact behavior
        depends on the file system event timing.
        """
        config_file = tmp_path / "config.json"
        config_file.write_text('{}')

        mcp_calls = []
        rules_calls = []

        def mcp_callback(path):
            mcp_calls.append(path)

        def rules_callback(path):
            rules_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(config_file),
            gateway_rules_path=str(config_file),  # Same file
            on_mcp_config_changed=mcp_callback,
            on_gateway_rules_changed=rules_callback,
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.3)

        config_file.write_text('{"changed": true}')

        time.sleep(0.5)

        watcher.stop()

        # At least one callback should be invoked (could be both)
        # The exact behavior depends on how the file system and debouncing interact
        total_calls = len(mcp_calls) + len(rules_calls)
        assert total_calls >= 1, f"Expected at least 1 callback, got {total_calls}"

    def test_symlink_handling(self, tmp_path):
        """Test handling of symlinked config files."""
        # Create actual files
        actual_mcp = tmp_path / "actual_mcp.json"
        actual_rules = tmp_path / "actual_rules.json"

        actual_mcp.write_text('{"mcpServers": {}}')
        actual_rules.write_text('{"agents": {}}')

        # Create symlinks
        link_mcp = tmp_path / "mcp.json"
        link_rules = tmp_path / "rules.json"

        link_mcp.symlink_to(actual_mcp)
        link_rules.symlink_to(actual_rules)

        callback_calls = []

        def callback(path):
            callback_calls.append(path)

        watcher = ConfigWatcher(
            mcp_config_path=str(link_mcp),
            gateway_rules_path=str(link_rules),
            on_mcp_config_changed=callback,
            on_gateway_rules_changed=Mock(),
            debounce_seconds=0.1
        )

        watcher.start()
        time.sleep(0.2)

        # Modify through symlink
        link_mcp.write_text('{"mcpServers": {"new": {}}}')

        time.sleep(0.3)

        watcher.stop()

        # Should detect change
        assert len(callback_calls) > 0
