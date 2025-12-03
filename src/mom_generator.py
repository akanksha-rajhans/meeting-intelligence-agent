# src/mom_generator.py
from typing import List, Dict, Optional
from src.extractor import extract_mom_actions
from src.db_actions import save_actions
from src.notifier import Notifier
from src.config import SLACK_BOT_TOKEN  # adjust if your config differs

def generate_mom(
    transcript: str,
    attendees: List[Dict],
    meeting_date: str,
    meeting_id: Optional[str] = None,
    slack_channel: Optional[str] = None
) -> dict:
    slack_channel = slack_channel
    data = extract_mom_actions(transcript, attendees, meeting_date)
    actions = data.get("actions", [])
    if not actions:
        return data

    # 1) Persist actions (this generates id & slack_action_id and commits)
    saved_actions = save_actions(actions, meeting_id or meeting_date)

    # 2) Send Slack messages using the same slack_action_id so clicks map to DB
    notifier = Notifier(token=SLACK_BOT_TOKEN, default_channel=slack_channel)
    for act in saved_actions:
        try:
            notifier.send_action_card(act, meeting_title=meeting_id or meeting_date)
        except Exception as e:
            print(f"[WARN] failed to send action card for {act.get('slack_action_id')}: {e}")

    return data
