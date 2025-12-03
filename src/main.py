# src/main.py
"""
Main pipeline for meeting-agent:
- main()       : process the latest / manual flow (audio dir -> MOM -> Slack)
- process_once : entry used by auto_watch to process a single video file
"""
from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from datetime import datetime

# package-qualified imports (works when running `python -m src.auto_watch`)
from src import config
from src.notifier import SlackNotifier
from src.audio_utils import pick_up_audio_single
from src.zoom_watcher import pick_up_audio
from src.transcriber import transcribe_audio
from src.mom_generator import generate_mom
from src.db_actions import save_actions

# setup logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# constants / defaults
ATTENDEES = [
    {"name": "Akanksha Rajhans", "email": "akanksha.rajhans@oracle.com"}
]
MEETING_TITLE = "Zoom Call"

# Determine default channel: prefer explicit env SLACK_CHANNEL_ID, then config.DEFAULT_CHANNEL, then fallback name
_default_channel = os.getenv("SLACK_CHANNEL_ID") or getattr(config, "DEFAULT_CHANNEL", None) or "all-meeting-agent"
_slack_token = config.SLACK_BOT_TOKEN

# helper to create a notifier with safe defaults
def make_notifier(token: str | None = None, channel: str | None = None) -> SlackNotifier:
    token = token or _slack_token
    if not token:
        raise RuntimeError("Slack bot token not configured (SLACK_BOT_TOKEN).")
    channel = channel or _default_channel
    return SlackNotifier(token=token, default_channel=channel)


def main():
    logger.info("🚀  Zoom-Recordings → MOM → Slack")
    # 1. pick up audio (manual helper that may watch a dir or pick newest)
    audio_path = pick_up_audio()
    logger.info("🎧 Audio picked: %s", audio_path)

    # 2. use the file name as meeting id/title
    meeting_title = audio_path.stem   # ⭐ THIS IS BEST

    # 3. transcribe
    transcript = transcribe_audio(audio_path)
    logger.info("📝 Transcript length: %d chars", len(transcript) if transcript else 0)

    # 4. generate MOM + actions
    data = generate_mom(transcript, ATTENDEES, datetime.now().strftime("%Y-%m-%d"))
    save_actions(data["actions"], meeting_title)

    # 5. save local copy
    mom_file = config.PROCESSED_DIR / f"{audio_path.stem}_MOM.json"
    mom_file.write_text(json.dumps(data, indent=2))
    logger.info("💾  MOM saved: %s", mom_file.name)

    # 6. send to Slack
    notifier = make_notifier()
    notifier.send_mom_card(data["mom"], data["actions"], MEETING_TITLE, datetime.now().strftime("%Y-%m-%d"))
    logger.info("🎉  All done – check your Slack channel and DMs")


def process_once(file_path: Path):
    """Entry-point for auto-watch (single file)."""
    meeting_title = file_path.stem
    attendees = ATTENDEES

    try:
        # 1. extract audio
        audio_path = pick_up_audio_single(file_path, out_dir=config.PROCESSED_DIR)
        logger.info("Extracted audio: %s", audio_path)

        save_actions(data["actions"], meeting_title)

        # 2. transcribe
        transcript = transcribe_audio(audio_path)

        # 3. generate MOM + actions
        data = generate_mom(transcript, attendees, datetime.now().strftime("%Y-%m-%d"))

        # 4. send to Slack
        notifier = make_notifier()
        notifier.send_mom_card(data["mom"], data["actions"], meeting_title, datetime.now().strftime("%Y-%m-%d"))

        logger.info("✅  Pipeline finished for %s", file_path.name)
    except Exception:
        logger.exception("Pipeline failed for %s", file_path.name)
        raise


if __name__ == "__main__":
    main()
