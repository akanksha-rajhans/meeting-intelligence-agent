# src/db_actions.py
import sqlite3
import uuid
from pathlib import Path
from typing import List, Dict
from src.config import PROCESSED_DIR

DB_PATH = PROCESSED_DIR / "meeting_agent.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS action_items (
        id TEXT PRIMARY KEY,
        meeting_id TEXT NOT NULL,
        task TEXT,
        owner_email TEXT,
        owner TEXT,
        due_date TEXT,
        priority TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        slack_message_ts TEXT,
        snoozed_until TEXT,
        deleted_at TEXT,
        slack_action_id TEXT
    )
    """)

    con.commit()
    con.close()
    ensure_index()

def ensure_index():
    """
    Create unique index on slack_action_id for fast lookup and to avoid duplicates.
    This is idempotent.
    """
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
      CREATE UNIQUE INDEX IF NOT EXISTS ux_action_items_slack_action_id
      ON action_items(slack_action_id)
    """)
    con.commit()
    con.close()


def save_actions(actions: List[Dict], meeting_id: str) -> List[Dict]:
    """
    Persist actions to DB while ensuring each action has a stable id and slack_action_id.
    Returns the list of actions with 'id' and 'slack_action_id' populated.
    """
    init_db()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    saved = []
    for a in actions:
        # if the model returned an id, keep it; otherwise generate a stable UUID
        action_id = a.get("id") or str(uuid.uuid4())
        # use slack_action_id if provided, otherwise use the same uuid
        slack_action_id = a.get("slack_action_id") or action_id

        # Upsert: use INSERT OR REPLACE so repeated runs don't duplicate
        cur.execute("""
            INSERT OR REPLACE INTO action_items
            (id, meeting_id, task, owner_email, owner, due_date, priority, status, created_at, slack_action_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT status FROM action_items WHERE id = ?), 'pending'), datetime('now'), ?)
        """, (
            action_id,
            meeting_id,
            a.get("task"),
            a.get("owner_email"),
            a.get("owner"),
            a.get("deadline"),   # stored into due_date column
            a.get("priority"),
            action_id,           # for COALESCE lookup (existing status if present)
            slack_action_id
        ))

        saved_action = dict(a)  # copy original
        saved_action["id"] = action_id
        saved_action["slack_action_id"] = slack_action_id
        saved.append(saved_action)

    con.commit()
    con.close()
    return saved


def find_by_slack_action_id(slack_action_id: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
      SELECT rowid, id, slack_action_id, task, status
      FROM action_items
      WHERE slack_action_id = ? OR id = ?
    """, (slack_action_id, slack_action_id))
    row = cur.fetchone()
    con.close()
    return row


def update_slack_message_ts(rowid: int, slack_ts: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("UPDATE action_items SET slack_message_ts = ? WHERE rowid = ?", (slack_ts, rowid))
    con.commit()
    con.close()
