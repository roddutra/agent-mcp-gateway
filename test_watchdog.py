#!/usr/bin/env python3
"""Test script to verify watchdog is working in this environment."""

import time
import os
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestHandler(FileSystemEventHandler):
    """Handler that logs all file system events."""

    def on_modified(self, event):
        logger.info(f"MODIFIED: {event.src_path} (is_directory: {event.is_directory})")
        print(f">>> MODIFIED: {event.src_path}")

    def on_created(self, event):
        logger.info(f"CREATED: {event.src_path} (is_directory: {event.is_directory})")
        print(f">>> CREATED: {event.src_path}")

    def on_deleted(self, event):
        logger.info(f"DELETED: {event.src_path} (is_directory: {event.is_directory})")
        print(f">>> DELETED: {event.src_path}")

    def on_moved(self, event):
        logger.info(f"MOVED: {event.src_path} -> {event.dest_path}")
        print(f">>> MOVED: {event.src_path} -> {event.dest_path}")


def main():
    """Run the watchdog test."""
    config_dir = Path(__file__).parent / "config"
    config_dir = config_dir.resolve()

    print(f"\n{'='*60}")
    print(f"Watchdog Test Script")
    print(f"{'='*60}\n")
    print(f"Watching directory: {config_dir}")
    print(f"Directory exists: {config_dir.exists()}")
    print(f"Directory is a directory: {config_dir.is_dir()}")

    if not config_dir.exists():
        print(f"\nERROR: Directory does not exist!")
        return

    # List files in the directory
    print(f"\nFiles in directory:")
    for file in sorted(config_dir.iterdir()):
        print(f"  - {file.name}")

    print(f"\n{'='*60}")
    print(f"Starting observer...")
    print(f"{'='*60}\n")

    handler = TestHandler()
    observer = Observer()
    observer.schedule(handler, str(config_dir), recursive=False)
    observer.start()

    print(f"Observer started (thread: {observer})")
    print(f"Observer is alive: {observer.is_alive()}\n")

    print(f"Now modify config/.mcp-gateway-rules.json and watch for events...")
    print(f"Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n\nStopping observer...")
        observer.stop()
        observer.join(timeout=2.0)
        print(f"Observer stopped")


if __name__ == "__main__":
    main()
