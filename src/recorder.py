"""
Zoom-recording *watcher*.
Picks up the newest file dropped into ZOOM_RECORDINGS_DIR
and returns the audio track (M4A or extracted MP3).
"""
import os
import time
import shutil
from pathlib import Path
from datetime import datetime
import subprocess
from src.config import PROCESSED_DIR, ZOOM_RECORDINGS_DIR

ZOOM_DIR = Path(ZOOM_RECORDINGS_DIR).expanduser().resolve()
AUDIO_OUT = PROCESSED_DIR   # where we put the final audio file

def _latest_file(folder: Path, extensions: tuple) -> Path | None:
    """Return the newest file with given suffixes."""
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in extensions]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None

def _extract_audio(video_path: Path) -> Path:
    """Extract 16 kHz mono MP3 from MP4/MOV."""
    out_path = AUDIO_OUT / f"{video_path.stem}.mp3"
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        "-y", str(out_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path

def pick_up_zoom_audio(timeout: int = 600) -> Path:
    """
    Wait until user drops a new Zoom recording into ZOOM_DIR,
    then return the audio track (M4A preferred, otherwise extracted MP3).
    """
    print(f"⏳  Waiting for new file in {ZOOM_DIR} …")
    seen = {f for f in ZOOM_DIR.iterdir() if f.is_file()}
    t0 = time.time()

    while time.time() - t0 < timeout:
        now = {f for f in ZOOM_DIR.iterdir() if f.is_file()}
        new_files = now - seen
        if new_files:
            newest = max(new_files, key=lambda f: f.stat().st_mtime)
            print(f"🆕  New file detected: {newest.name}")

            # Prefer M4A (Zoom cloud audio), else extract from MP4/MOV
            if newest.suffix.lower() == ".m4a":
                out_path = AUDIO_OUT / f"{newest.stem}.m4a"
                shutil.copy2(newest, out_path)
            elif newest.suffix.lower() in (".mp4", ".mov"):
                out_path = _extract_audio(newest)
            else:
                raise ValueError("Only .m4a, .mp4, .mov accepted")

            print(f"✅  Audio ready: {out_path.name}")
            return out_path

        time.sleep(2)

    raise TimeoutError("No new file arrived within 10 min")

def record_zoom_meeting() -> Path:
    """Entry-point compatible with old name."""
    return pick_up_zoom_audio()

if __name__ == "__main__":
    # quick test
    audio = pick_up_zoom_audio()
    print("🎉", audio)