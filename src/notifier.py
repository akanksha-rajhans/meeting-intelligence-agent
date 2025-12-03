# src/notifier.py
"""
Notifier for meeting-agent — complete implementation.

Drop this file into src/notifier.py to replace your current notifier.
Requires slack_sdk and a valid config.SLACK_BOT_TOKEN.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from uuid import uuid4

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Notifier:
    def __init__(self, token: str, default_channel: str, db_path: Optional[Path] = None):
        """
        token: bot token (xoxb-...)
        default_channel: channel id (C...) or name ('general')
        db_path: optional Path to meeting_agent.db
        """
        self.client = WebClient(token=token)
        self.default_channel = default_channel

        if db_path:
            self.db_path = Path(db_path)
        else:
            try:
                from src.config import PROCESSED_DIR  # type: ignore
                self.db_path = Path(PROCESSED_DIR) / "meeting_agent.db"
            except Exception:
                self.db_path = None
                logger.info("No db_path provided and PROCESSED_DIR not available; DB features disabled.")

        # ensure DB columns we'll use exist (idempotent)
        if self.db_path:
            try:
                self._ensure_db_columns(
                    {
                        "slack_message_ts": "TEXT",
                        "snoozed_until": "TEXT",
                        "deleted_at": "TEXT",
                    }
                )
            except Exception:
                logger.exception("Failed to ensure DB columns at init; continuing without migration.")

        self._email_to_uid_cache: Dict[str, str] = {}

    # -----------------------
    # Channel resolution & posting
    # -----------------------
    def _resolve_channel_id(self, channel: str) -> str:
        """
        Accepts channel id (C..., G..., D...) or plain name ('general' or '#general').
        Returns channel ID or raises RuntimeError with helpful message.
        """
        if not channel:
            raise RuntimeError("No channel provided to _resolve_channel_id")

        if channel.startswith(("C", "G", "D")):
            return channel

        if channel.startswith("#"):
            channel = channel[1:]

        try:
            cursor = None
            while True:
                resp = self.client.conversations_list(limit=200, cursor=cursor, types="public_channel,private_channel")
                if not resp.get("ok", False):
                    raise RuntimeError(f"conversations_list failed: {resp}")

                for ch in resp.get("channels", []):
                    if ch.get("name") == channel:
                        return ch["id"]

                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            raise RuntimeError(
                f"Channel with name '{channel}' not found. Make sure the bot is in the workspace and that the name is correct."
            )
        except SlackApiError as e:
            raise RuntimeError(f"Slack API error while listing channels: {e.response.get('error')} - check scopes and token.") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error resolving channel: {e}") from e

    # -----------------------
    # DB utilities / migrations
    # -----------------------
    def _get_table_columns(self, table: str) -> List[str]:
        if not self.db_path:
            return []
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            rows = cur.fetchall()
            return [r[1] for r in rows]
        finally:
            conn.close()

    def _ensure_db_columns(self, cols: Dict[str, str]) -> None:
        """
        Ensure the given columns exist on action_items table. cols is mapping name->SQL_TYPE.
        """
        if not self.db_path:
            logger.debug("DB path not configured; skipping _ensure_db_columns")
            return

        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(action_items)")
            existing = {r[1] for r in cur.fetchall()}

            for name, sql_type in cols.items():
                if name not in existing:
                    logger.info("Altering action_items: adding column %s %s", name, sql_type)
                    cur.execute(f"ALTER TABLE action_items ADD COLUMN {name} {sql_type}")
            conn.commit()
        finally:
            conn.close()

    def _execute_db(self, sql: str, params: tuple = ()) -> int:
        """Execute SQL and return rowcount."""
        if not self.db_path:
            logger.debug("DB path not configured; skipping DB exec")
            return 0
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def _save_ts(self, action_id: str, ts: str) -> None:
        if not self.db_path:
            logger.debug("DB path not configured; skipping _save_ts")
            return
        self._execute_db("UPDATE action_items SET slack_message_ts=? WHERE id=?", (ts, action_id))
        logger.debug("Saved slack_message_ts for action %s (ts=%s)", action_id, ts)

    # -----------------------
    # DB update helpers
    # -----------------------
    def mark_done(self, action_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        # try to update by slack_action_id first, fall back to id
        rowcount = self._execute_db(
            "UPDATE action_items SET status='completed', completed_at=? WHERE slack_action_id=? AND status!='deleted'",
            (now, action_id),
        )
        if rowcount == 0:
            rowcount = self._execute_db(
                "UPDATE action_items SET status='completed', completed_at=? WHERE id=? AND status!='deleted'",
                (now, action_id),
            )
        logger.info("mark_done: action=%s updated=%d", action_id, rowcount)
        return rowcount > 0


    def snooze_action(self, action_id: str, days: int = 1) -> bool:
        until = (datetime.utcnow() + timedelta(days=days)).isoformat()
        rowcount = self._execute_db(
            "UPDATE action_items SET snoozed_until=?, status='snoozed' WHERE slack_action_id=? AND status!='deleted'",
            (until, action_id),
        )
        if rowcount == 0:
            rowcount = self._execute_db(
                "UPDATE action_items SET snoozed_until=?, status='snoozed' WHERE id=? AND status!='deleted'",
                (until, action_id),
            )
        logger.info("snooze_action: action=%s snoozed_until=%s updated=%d", action_id, until, rowcount)
        return rowcount > 0


    def delete_action(self, action_id: str) -> bool:
        deleted_at = datetime.utcnow().isoformat()
        rowcount = self._execute_db(
            "UPDATE action_items SET status='deleted', deleted_at=? WHERE slack_action_id=?",
            (deleted_at, action_id),
        )
        if rowcount == 0:
            rowcount = self._execute_db(
                "UPDATE action_items SET status='deleted', deleted_at=? WHERE id=?",
                (deleted_at, action_id),
            )
        logger.info("delete_action: action=%s deleted_at=%s updated=%d", action_id, deleted_at, rowcount)
        return rowcount > 0

    # -----------------------
    # Slack helpers
    # -----------------------
    def _slack_id(self, email: str) -> Optional[str]:
        if not email:
            return None
        if email in self._email_to_uid_cache:
            return self._email_to_uid_cache[email]
        try:
            resp = self.client.users_lookupByEmail(email=email)
            uid = resp["user"]["id"]
            self._email_to_uid_cache[email] = uid
            return uid
        except SlackApiError as e:
            logger.warning("Could not resolve Slack user for %s: %s", email, e.response.get("error"))
            return None
        except Exception:
            logger.exception("Unexpected error resolving slack id for %s", email)
            return None

    def _open_dm(self, user_id: str) -> Optional[str]:
        try:
            resp = self.client.conversations_open(users=user_id)
            channel_id = resp["channel"]["id"]
            return channel_id
        except SlackApiError as e:
            logger.warning("Failed to open DM with %s: %s", user_id, e.response.get("error"))
            return None
        except Exception:
            logger.exception("Unexpected error opening DM with %s", user_id)
            return None

    # -----------------------
    # Action card posting
    # -----------------------
    def _build_action_blocks(self, action: Dict, meeting_title: str) -> List[Dict]:
        # Prefer persisted slack_action_id (new column). Fallback to id; if both missing, generate one and persist.
        action_id_str = None
        # 1) prefer slack_action_id if already present in the dict
        if action.get("slack_action_id"):
            action_id_str = str(action["slack_action_id"])
        # 2) else prefer primary key id (do NOT overwrite PK in DB)
        elif action.get("id") and str(action.get("id")).lower() != "none":
            action_id_str = str(action["id"])
        # 3) else generate a uuid and persist to DB (match by PK id if available)
        else:
            action_id_str = str(uuid4())
            action["slack_action_id"] = action_id_str
            # persist: if action has id (PK) use it to update slack_action_id, else skip persisting
            try:
                if action.get("id"):
                    self._execute_db("UPDATE action_items SET slack_action_id=? WHERE id=?", (action_id_str, action["id"]))
                    logger.info("Persisted generated slack_action_id %s for action id=%s", action_id_str, action.get("id"))
            except Exception:
                logger.exception("Failed to persist generated slack_action_id for action: %s", action.get("task"))

        # If slack_action_id absent but we have id, try to copy id->slack_action_id in-memory (not persisted)
        if not action.get("slack_action_id") and action.get("id"):
            action["slack_action_id"] = action_id_str

        # DEBUG log
        logger.debug("Action send id used: %s (orig id=%s task=%s)", action_id_str, action.get("id"), action.get("task"))

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Action from {meeting_title}*\n{action.get('task', '')}"},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*Owner:* {action.get('owner', action.get('owner_email', 'N/A'))}"},
                    {"type": "mrkdwn", "text": f"*Due:* {action.get('deadline', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Priority:* {action.get('priority', 'N/A')}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Mark Complete"},
                        "action_id": f"mark_done_{action_id_str}",
                        "value": action_id_str,
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "⏰ Snooze 1d"},
                        "action_id": f"snooze_1d_{action_id_str}",
                        "value": action_id_str,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🗑️ Delete"},
                        "action_id": f"delete_{action_id_str}",
                        "value": action_id_str,
                        "style": "danger",
                    },
                ],
            },
        ]
        return blocks

    def send_action_card(self, action: Dict, meeting_title: str) -> bool:
        owner_email = action.get("owner_email") or action.get("owner")
        if not owner_email:
            logger.info("Action %s has no owner_email; skipping", action.get("id"))
            return False

        uid = self._slack_id(owner_email)
        if not uid:
            logger.info("No Slack user for email %s; skipping action %s", owner_email, action.get("id"))
            return False

        channel = self._open_dm(uid)
        if not channel:
            logger.info("Could not open DM for user %s; skipping", uid)
            return False

        action_id_str = str(action.get("slack_action_id") or action.get("id") or uuid4())
        # persist if slack_action_id was missing and we have PK id
        if not action.get("slack_action_id") and action.get("id"):
            action["slack_action_id"] = action_id_str
            try:
                self._execute_db("UPDATE action_items SET slack_action_id=? WHERE id=?", (action_id_str, action["id"]))
                logger.info("Persisted slack_action_id=%s for action id=%s", action_id_str, action.get("id"))
            except Exception:
                logger.exception("Failed to persist slack_action_id for action id=%s", action.get("id"))
        # ensure action dict is updated so quick buttons match
        action["id"] = action_id_str
        blocks = self._build_action_blocks(action, meeting_title)
        logger.debug("Posting Slack DM to uid=%s for action id=%s task=%s", uid, action_id_str, action.get("task"))

        try:
            from src.slack_buttons import send_via_bolt
            resp = send_via_bolt(channel=channel, text=f"Action: {action.get('task', '')}", blocks=blocks)
            ts = resp.get("ts")
            if ts:
                self._save_ts(action_id_str, ts)
            logger.info("Posted action %s to user %s (ts=%s)", action_id_str, uid, ts)
            return True
        except SlackApiError as e:
            logger.warning("Slack API error sending action %s to %s: %s", action_id_str, uid, e.response.get("error"))
            return False
        except Exception:
            logger.exception("Unexpected error sending action %s to %s", action_id_str, uid)
            return False

    def send_bulk_action_cards(self, actions: List[Dict], meeting_title: str) -> int:
        success = 0
        for a in actions:
            try:
                if self.send_action_card(a, meeting_title):
                    success += 1
            except Exception:
                logger.exception("Error sending action card for %s", a.get("id"))
        logger.info("send_bulk_action_cards: posted %d/%d", success, len(actions))
        return success

    # -----------------------
    # Existing mom card preserved
    # -----------------------
    def send_mom_card(self, mom_text: str, actions: List[Dict], meeting_title: str, meeting_date: str, channel: Optional[str] = None):
        channel = channel or self.default_channel
        try:
            channel_id = self._resolve_channel_id(channel)
        except Exception as e:
            logger.error("Failed to resolve channel id: %s", e)
            raise

        fallback_text = f"MOM: {meeting_title} ({meeting_date}) — {mom_text[:240]}"

        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{meeting_title}* — {meeting_date}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": mom_text}},
        ]

        if actions:
            actions_md = "\n".join(
                [
                    f"*{a.get('task')}* — {a.get('owner') or a.get('owner_email', 'N/A')} — due: {a.get('deadline') or 'N/A'} — priority: {a.get('priority')}"
                    for a in actions
                ]
            )
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Actions*\n" + actions_md}})

            # Defensive: persist any actions missing id/slack_action_id so buttons map to DB
            try:
                from src import db_actions  # type: ignore

                need_persist = any(not (a.get("slack_action_id") or a.get("id")) for a in actions)
                if need_persist:
                    actions_for_buttons = db_actions.save_actions(actions, meeting_title)
                    logger.info("send_mom_card: persisted missing actions before quick buttons")
                else:
                    actions_for_buttons = actions
            except Exception:
                logger.exception("send_mom_card: failed to persist actions; falling back to provided list")
                actions_for_buttons = actions

            quick_elements = []
            for a in actions_for_buttons[:3]:
                # prefer slack_action_id, then id
                aid_raw = a.get("slack_action_id") or a.get("id")
                if not aid_raw:
                    logger.warning("send_mom_card: skipping action without id/slack_action_id (task=%s)", a.get("task"))
                    continue

                aid = str(aid_raw)
                # normalize action dict so other codepaths see consistent ids
                a["id"] = aid
                a["slack_action_id"] = aid

                quick_elements.append(
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": f"Mark {aid[:8]} Done"},
                        "action_id": f"mark_done_{aid}",
                        "value": aid,
                        "style": "primary",
                    }
                )

            if quick_elements:
                blocks.append({"type": "actions", "elements": quick_elements})

        # Try to send via Bolt's helper (preferred) then fallback to WebClient
        try:
            from src.slack_buttons import send_via_bolt  # type: ignore
            logger.debug("Posting MOM to channel_id=%s with %d quick buttons", channel_id, len(blocks))
            resp = send_via_bolt(channel=channel_id, text=fallback_text, blocks=blocks)
            if not resp.get("ok", True):
                raise RuntimeError(f"Slack chat.postMessage returned not ok: {resp}")

            # Save slack_message_ts for the first quick button's action if present
            if resp:
                ts = resp.get("ts")
                if ts:
                    first_aid = None
                    for e in blocks:
                        if e.get("type") == "actions":
                            elems = e.get("elements", [])
                            if elems:
                                first_aid = elems[0].get("value")
                                break
                    if first_aid:
                        try:
                            from src import db_actions as _db  # type: ignore
                            row = _db.find_by_slack_action_id(first_aid)
                            if row:
                                rowid = row[0]
                                self._save_ts(rowid, ts)
                        except Exception:
                            logger.exception("Failed to save slack_message_ts for action %s", first_aid)

            logger.info("MOM posted to Slack channel %s (ts=%s)", channel_id, resp.get("ts"))
            return resp
        except SlackApiError as e:
            err = e.response.get("error", "")
            if err == "channel_not_found":
                raise RuntimeError("Slack channel not found. Check channel id/name and that the bot is invited to the channel.") from e
            elif err in ("not_in_channel", "is_archived"):
                raise RuntimeError(f"Bot cannot post to channel: {err}. Invite the bot or unarchive the channel.") from e
            elif err in ("missing_scope", "invalid_auth"):
                raise RuntimeError("Slack token is invalid or missing required scopes (chat:write, conversations:read). Check token and OAuth scopes.") from e
            else:
                raise RuntimeError(f"Slack API error: {err}") from e
        except Exception:
            # fallback — use WebClient (non-interactive; buttons may not work if bolt not running)
            logger.warning("Bolt send_via_bolt unavailable; falling back to WebClient.chat_postMessage")
            resp = self.client.chat_postMessage(channel=channel_id, text=fallback_text, blocks=blocks)
            # attempt to save slack_message_ts after fallback send
            try:
                if resp and resp.get("ts"):
                    first_aid = None
                    for e in blocks:
                        if e.get("type") == "actions":
                            elems = e.get("elements", [])
                            if elems:
                                first_aid = elems[0].get("value")
                                break
                    if first_aid:
                        from src import db_actions as _db  # type: ignore
                        row = _db.find_by_slack_action_id(first_aid)
                        if row:
                            rowid = row[0]
                            self._save_ts(rowid, resp.get("ts"))
            except Exception:
                logger.exception("Failed to save slack_message_ts after fallback send")
            return resp


# Backwards-compatible alias
SlackNotifier = Notifier