# src/zoom_watcher.py
"""
Watch / process Zoom media files.

Functions:
- pick_up_audio_single(file_path: Path) -> Path
- pick_up_audio(timeout: int = 600) -> Path
"""
from __future__ import annotations

import time
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional

from src.config import ZOOM_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _latest_media(folder: Path) -> Optional[Path]:
    files = [f for f in folder.iterdir() if f.suffix.lower() in (".mp4", ".m4a", ".mov")]
    return max(files, key=lambda x: x.stat().st_mtime) if files else None


def _ensure_ffmpeg() -> str:
    """Return ffmpeg binary path or raise helpful error."""
    from shutil import which

    ff = which("ffmpeg")
    if not ff:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it (macOS: `brew install ffmpeg`, Ubuntu: `sudo apt install ffmpeg`)."
        )
    return ff


def _extract_audio(video: Path, out_path: Optional[Path] = None) -> Path:
    ffmpeg_bin = _ensure_ffmpeg()
    out = out_path if out_path else (PROCESSED_DIR / f"{video.stem}.mp3")
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-v", "error",
        "-y",
        "-i", str(video),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-b:a", "64k",
        str(out),
    ]
    logger.info("Extracting audio: %s -> %s", video.name, out.name)
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        raise RuntimeError(f"ffmpeg failed extracting audio: {stderr}") from e

    if not out.exists():
        raise RuntimeError(f"ffmpeg reported success but output missing: {out}")

    return out


def pick_up_audio_single(file_path: Path) -> Path:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if file_path.suffix.lower() == ".m4a":
        dst = PROCESSED_DIR / file_path.name
        logger.info("Copying m4a to processed: %s", dst.name)
        shutil.copy2(file_path, dst)
        return dst
    else:
        return _extract_audio(file_path)


def pick_up_audio(timeout: int = 600) -> Path:
    """Watch ZOOM_DIR for a new media file for up to `timeout` seconds."""
    print(f"⏳  Waiting for new media in {ZOOM_DIR} …")
    ZOOM_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    seen = {f for f in ZOOM_DIR.iterdir() if f.is_file()}
    t0 = time.time()

    while time.time() - t0 < timeout:
        now = {f for f in ZOOM_DIR.iterdir() if f.is_file()}
        new = now - seen
        if new:
            newest = max(new, key=lambda x: x.stat().st_mtime)
            print(f"🆕  New file: {newest.name}")
            # small pause to avoid reading a partially-written file
            time.sleep(1.0)
            try:
                audio = pick_up_audio_single(newest)
                return audio
            except Exception as e:
                logger.exception("Failed to process incoming file %s: %s", newest.name, e)
                # update seen and continue watching
                seen = now
                time.sleep(1.0)
                continue
        time.sleep(1.0)

    raise TimeoutError(f"No new media detected in {ZOOM_DIR} within {timeout} seconds.")
