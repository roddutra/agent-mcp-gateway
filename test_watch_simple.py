#!/usr/bin/env python3
"""Simple test to verify watchdog detects config file changes."""

import time
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os

class SimpleHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if not event.is_directory:
            print(f"Event: {event.event_type} - {event.src_path}", flush=True)

# Watch the config directory
config_dir = os.path.abspath("config")
print(f"Watching: {config_dir}", flush=True)
print("Modify config/.mcp-gateway-rules.json now...", flush=True)

handler = SimpleHandler()
observer = Observer()
observer.schedule(handler, config_dir, recursive=False)
observer.start()

print("Watching started. Will run for 30 seconds...", flush=True)
try:
    time.sleep(30)
except KeyboardInterrupt:
    pass
finally:
    observer.stop()
    observer.join()
    print("Stopped", flush=True)
