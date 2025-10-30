"""Configuration file watcher for hot reloading."""

import logging
import threading
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watches configuration files for changes and triggers reload callbacks.

    The watcher monitors two configuration files (.mcp.json and .mcp-gateway-rules.json)
    and calls the appropriate callback when changes are detected. It implements debouncing
    to handle rapid file system events (e.g., editor saves that create temporary files).

    Thread Safety:
        The watchdog Observer runs in a separate thread. Callbacks are invoked from that
        thread, so they must be thread-safe. The debouncing timer also runs in a separate
        thread context.

    Example:
        ```python
        def on_mcp_config_changed(config_path: str):
            logger.info(f"Reloading MCP config from: {config_path}")
            # Reload logic here

        def on_rules_changed(rules_path: str):
            logger.info(f"Reloading gateway rules from: {rules_path}")
            # Reload logic here

        watcher = ConfigWatcher(
            mcp_config_path="/path/to/.mcp.json",
            gateway_rules_path="/path/to/.mcp-gateway-rules.json",
            on_mcp_config_changed=on_mcp_config_changed,
            on_gateway_rules_changed=on_rules_changed,
            debounce_seconds=0.3
        )

        watcher.start()
        # ... application runs ...
        watcher.stop()
        ```
    """

    def __init__(
        self,
        mcp_config_path: str,
        gateway_rules_path: str,
        on_mcp_config_changed: Callable[[str], None],
        on_gateway_rules_changed: Callable[[str], None],
        debounce_seconds: float = 0.1,  # Reduced from 0.3 for faster response
    ):
        """Initialize the configuration file watcher.

        Args:
            mcp_config_path: Path to .mcp.json file (can be relative or absolute,
                will be resolved to absolute path)
            gateway_rules_path: Path to .mcp-gateway-rules.json file (can be relative or
                absolute, will be resolved to absolute path)
            on_mcp_config_changed: Callback invoked when MCP config changes.
                Receives the resolved absolute config file path as argument.
            on_gateway_rules_changed: Callback invoked when gateway rules change.
                Receives the resolved absolute rules file path as argument.
            debounce_seconds: Time to wait after last file event before triggering
                callback. Prevents multiple rapid callbacks from editor autosaves.
                Default: 0.3 seconds.
        """
        # Validate and normalize paths to absolute
        self.mcp_config_path = Path(mcp_config_path).resolve()
        self.gateway_rules_path = Path(gateway_rules_path).resolve()

        # Store callbacks
        self.on_mcp_config_changed = on_mcp_config_changed
        self.on_gateway_rules_changed = on_gateway_rules_changed
        self.debounce_seconds = debounce_seconds

        # Initialize observer and handler
        self.observer: Observer | None = None
        self._event_handler = _ConfigFileEventHandler(self)
        self._lock = threading.Lock()

        # Debouncing state (protected by lock)
        self._pending_timers: dict[str, threading.Timer] = {}

        logger.debug(
            f"ConfigWatcher initialized for MCP config: {self.mcp_config_path}, "
            f"Gateway rules: {self.gateway_rules_path}"
        )

    def start(self) -> None:
        """Start watching the configuration files.

        Creates a watchdog Observer and starts monitoring the directories containing
        the configuration files. The observer runs in a separate thread.

        Raises:
            RuntimeError: If watcher is already running
            OSError: If directories cannot be watched (e.g., permission denied)
        """
        with self._lock:
            if self.observer is not None:
                raise RuntimeError("ConfigWatcher is already running")

            # Get parent directories to watch
            mcp_config_dir = self.mcp_config_path.parent
            rules_dir = self.gateway_rules_path.parent

            # Create and start observer
            self.observer = Observer()

            # Watch MCP config directory
            try:
                self.observer.schedule(
                    self._event_handler, str(mcp_config_dir), recursive=False
                )
                logger.debug(f"Watching directory: {mcp_config_dir}")
            except OSError as e:
                raise OSError(
                    f"Cannot watch MCP config directory {mcp_config_dir}: {e}"
                ) from e

            # Watch gateway rules directory (if different)
            if rules_dir != mcp_config_dir:
                try:
                    self.observer.schedule(
                        self._event_handler, str(rules_dir), recursive=False
                    )
                    logger.debug(f"Watching directory: {rules_dir}")
                except OSError as e:
                    raise OSError(
                        f"Cannot watch gateway rules directory {rules_dir}: {e}"
                    ) from e

            self.observer.start()
            logger.info(
                f"ConfigWatcher started monitoring: {self.mcp_config_path.name}, "
                f"{self.gateway_rules_path.name}"
            )

    def stop(self) -> None:
        """Stop watching the configuration files and clean up resources.

        Stops the observer thread and cancels any pending debounce timers.
        This method is idempotent and safe to call multiple times.
        """
        with self._lock:
            # Cancel all pending timers
            for timer in self._pending_timers.values():
                timer.cancel()
            self._pending_timers.clear()

            # Stop and cleanup observer
            if self.observer is not None:
                self.observer.stop()
                self.observer.join(timeout=2.0)
                self.observer = None
                logger.info("ConfigWatcher stopped")

    def _handle_file_change(self, file_path: Path) -> None:
        """Handle a file change event with debouncing.

        This method is called by the event handler when a relevant file changes.
        It implements debouncing by canceling any pending timer for the file and
        starting a new one. The callback is only invoked after the debounce period
        elapses without new events.

        Args:
            file_path: Absolute path to the file that changed

        Thread Safety:
            Must be called with self._lock held, or from event handler which
            manages its own locking.
        """
        file_path = file_path.resolve()
        logger.debug(f"File change detected: {file_path}")

        # Determine which callback to use
        callback: Callable[[str], None] | None = None
        if file_path == self.mcp_config_path:
            callback = self.on_mcp_config_changed
            callback_name = "on_mcp_config_changed"
        elif file_path == self.gateway_rules_path:
            callback = self.on_gateway_rules_changed
            callback_name = "on_gateway_rules_changed"
        else:
            # Not one of our watched files (could be temp file, other file in dir, etc.)
            logger.debug(f"Ignoring change to non-watched file: {file_path}")
            return

        with self._lock:
            # Cancel existing timer for this file if any
            file_key = str(file_path)
            if file_key in self._pending_timers:
                self._pending_timers[file_key].cancel()
                logger.debug(f"Cancelled previous debounce timer for: {file_path.name}")

            # Create new debounced callback
            def debounced_callback():
                logger.info(
                    f"Config file changed after debounce period: {file_path.name}"
                )
                try:
                    callback(str(file_path))
                    logger.debug(f"Successfully invoked {callback_name}")
                except Exception as e:
                    logger.error(
                        f"Error in {callback_name} callback: {e}", exc_info=True
                    )
                finally:
                    # Clean up timer reference
                    with self._lock:
                        self._pending_timers.pop(file_key, None)

            # Schedule new timer
            timer = threading.Timer(self.debounce_seconds, debounced_callback)
            timer.daemon = True
            self._pending_timers[file_key] = timer
            timer.start()
            logger.debug(
                f"Scheduled debounced callback for {file_path.name} "
                f"in {self.debounce_seconds}s"
            )


class _ConfigFileEventHandler(FileSystemEventHandler):
    """Internal event handler for file system events.

    This handler filters file system events and forwards relevant ones
    (modified, created, moved) to the ConfigWatcher for debounced processing.
    """

    def __init__(self, watcher: ConfigWatcher):
        """Initialize the event handler.

        Args:
            watcher: The ConfigWatcher instance to notify of changes
        """
        super().__init__()
        self.watcher = watcher

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events.

        Args:
            event: The file system event
        """
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events.

        Some editors create new files when saving (write to temp, rename to target).

        Args:
            event: The file system event
        """
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename events.

        Many editors use atomic writes: write to temp file, then rename to target.
        We need to detect when a file is moved TO our watched config file path.

        Args:
            event: The file system event
        """
        if not event.is_directory and hasattr(event, "dest_path"):
            # Check if destination is one of our watched files
            self._handle_event(event.dest_path)

    def _handle_event(self, path: str) -> None:
        """Process a file system event path.

        Args:
            path: Path to the file that changed
        """
        try:
            file_path = Path(path).resolve()
            logger.debug(f"[EventHandler] Processing event for: {path}")
            logger.debug(f"[EventHandler] Resolved to: {file_path}")
            logger.debug(f"[EventHandler] Watched MCP config: {self.watcher.mcp_config_path}")
            logger.debug(f"[EventHandler] Watched gateway rules: {self.watcher.gateway_rules_path}")
            logger.debug(f"[EventHandler] Matches MCP config: {file_path == self.watcher.mcp_config_path}")
            logger.debug(f"[EventHandler] Matches gateway rules: {file_path == self.watcher.gateway_rules_path}")

            self.watcher._handle_file_change(file_path)
        except Exception as e:
            logger.error(f"Error handling file system event for {path}: {e}", exc_info=True)
