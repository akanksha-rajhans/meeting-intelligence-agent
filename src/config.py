# src/config.py — safe env-based configuration
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "meeting_agent.db")
PROCESSED_DIR = str(ROOT / "processed")

def _get_env(name: str, required: bool = False):
    """Helper to fetch environment variables. Raises only if required=True."""
    val = os.getenv(name)
    if required and not val:
        raise RuntimeError(f"Required environment variable {name} not set")
    return val

# ---------------- API KEYS / TOKENS ----------------
# Read secrets from environment only (DO NOT hardcode here).
ASSEMBLYAI_API_KEY = _get_env("ASSEMBLYAI_API_KEY", required=False)
GEMINI_API_KEY     = _get_env("GEMINI_API_KEY", required=False)
OPENAI_API_KEY     = _get_env("OPENAI_API_KEY", required=False)

SLACK_BOT_TOKEN    = _get_env("SLACK_BOT_TOKEN", required=False)   # xoxb-...
SLACK_APP_TOKEN    = _get_env("SLACK_APP_TOKEN", required=False)   # xapp-... (Socket Mode)

DEFAULT_CHANNEL    = os.getenv("DEFAULT_CHANNEL", "all-meeting-agent")

# Optional: small helper to show which envs are set (do not log tokens)
def env_status():
    return {
        "ASSEMBLYAI": bool(ASSEMBLYAI_API_KEY),
        "GEMINI": bool(GEMINI_API_KEY),
        "OPENAI": bool(OPENAI_API_KEY),
        "SLACK_BOT": bool(SLACK_BOT_TOKEN),
        "SLACK_APP": bool(SLACK_APP_TOKEN),
    }
