# src/auto_watch.py
"""
Simple polling watcher for Zoom recordings. Runs as a package:
    python -m src.auto_watch

When a new file appears in ZOOM_DIR, calls src.main.process_once(Path)
"""
from __future__ import annotations

import time
import logging
from pathlib import Path
from datetime import datetime

from src.config import ZOOM_DIR, LOGS_DIR
from src.zoom_watcher import pick_up_audio_single
from src.main import process_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("auto_watch")

POLL_INTERVAL = 2.0  # seconds
DEBOUNCE = 1.0       # seconds to wait after detection before processing


def _snapshot_files(folder: Path):
    return {p for p in folder.iterdir() if p.is_file()}


def main_loop():
    ZOOM_DIR.mkdir(parents=True, exist_ok=True)
    seen = _snapshot_files(ZOOM_DIR)
    logger.info("Watching %s for new recordings...", ZOOM_DIR)

    while True:
        try:
            now = _snapshot_files(ZOOM_DIR)
            new = now - seen
            if new:
                newest = max(new, key=lambda x: x.stat().st_mtime)
                logger.info("Detected new file: %s", newest.name)
                # wait a bit so file write completes
                time.sleep(DEBOUNCE)
                try:
                    process_once(newest)
                except Exception:
                    logger.exception("Processing failed for %s", newest.name)
                # update seen snapshot after processing so duplicates aren't reprocessed
                seen = _snapshot_files(ZOOM_DIR)
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Watcher stopped by user")
            break
        except Exception:
            logger.exception("Unexpected error in watcher loop; continuing")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main_loop()
