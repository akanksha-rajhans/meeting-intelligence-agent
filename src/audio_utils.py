# src/audio_utils.py
"""
Utilities to extract audio from video files.

pick_up_audio_single(file_path: str|Path) -> Path
- extracts audio using ffmpeg (recommended)
- returns Path to the created audio file (mp3)
- raises RuntimeError on failure
"""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
import logging
import re

from typing import Union

logger = logging.getLogger(__name__)


def _safe_basename(path: Union[str, Path]) -> str:
    """
    Create a filesystem-safe basename (keeps extension).
    Removes problematic unicode/characters for downstream tools.
    """
    p = Path(path)
    name = p.stem
    # Replace runs of whitespace with single underscore, remove control chars
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^\w\-\_\.]", "", name)
    return f"{name}{p.suffix}"


def _ensure_ffmpeg() -> str:
    """Return ffmpeg binary path or raise helpful error."""
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    raise RuntimeError(
        "ffmpeg not found on PATH. Install it (macOS: `brew install ffmpeg`, Ubuntu: `sudo apt install ffmpeg`)."
    )


def pick_up_audio_single(file_path: Union[str, Path], out_dir: Union[str, Path] | None = None) -> Path:
    """
    Extract audio from `file_path` and write an mp3 to out_dir (or same folder if not provided).
    Returns Path to the created audio file.

    Uses ffmpeg via subprocess for robust behaviour (handles spaces correctly).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise RuntimeError(f"Input file not found: {file_path}")

    out_dir = Path(out_dir) if out_dir else file_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # create a safe output filename based on original file
    safe_name = _safe_basename(file_path)
    # drop extension and append _audio.mp3
    base = Path(safe_name).stem
    out_file = out_dir / f"{base}_audio.mp3"

    ffmpeg_bin = _ensure_ffmpeg()

    cmd = [
        ffmpeg_bin,
        "-v", "error",           # show only errors
        "-y",                    # overwrite output
        "-i", str(file_path),
        "-vn",                   # no video
        "-acodec", "libmp3lame", # mp3 encoder
        "-ac", "2",              # stereo
        "-ar", "44100",          # 44.1k sample rate
        str(out_file),
    ]

    logger.info("Extracting audio: %s -> %s", file_path, out_file)
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        # include stderr in the error message
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        raise RuntimeError(f"ffmpeg failed extracting audio: {stderr}") from e

    if not out_file.exists():
        raise RuntimeError("ffmpeg reported success but output file missing: " + str(out_file))

    return out_file
