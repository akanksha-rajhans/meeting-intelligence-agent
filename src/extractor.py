# extractor.py
import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

API_KEY = os.getenv("GEMINI_API_KEY")
assert API_KEY, "GEMINI_API_KEY not found in environment"

# Choose a model your key can access. If you get 404/403, list models and replace accordingly.
# Examples you might see: "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent"

HEADERS = {
    "Content-Type": "application/json",
    "x-goog-api-key": API_KEY
}

# System instructions are embedded as the first 'user' message but labelled clearly.
SYSTEM_INSTRUCTION_TEXT = (
    "SYSTEM INSTRUCTION: You are a meeting-minutes assistant. "
    "Output ONLY valid JSON (no markdown, no explanations, no extra text). "
    "Return an object exactly matching this schema:\n"
    "{\n"
    '  "mom": "2-3 paragraph summary",\n'
    '  "actions": [\n'
    '    {\n'
    '      "task": "specific action",\n'
    '      "owner": "Name or UNASSIGNED",\n'
    '      "deadline": "YYYY-MM-DD or null",\n'
    '      "priority": "high/medium/low"\n'
    '    }\n'
    '  ]\n'
    "}\n"
    "Rules:\n"
    '- If a speaker says \"I\'ll ...\" assign that action to that speaker (use full name if present).\n'
    '- If a speaker says a weekday like \"Friday\", convert to the next calendar Friday date (relative to meeting date) in YYYY-MM-DD format.\n'
    '- If there are no actions, return \"actions\": [].\n'
    '- If you cannot output valid JSON, return exactly {\"error\":\"invalid_response\"}.\n'
)

# ---------------------- Helpers for response parsing ---------------------- #
def _find_generated_text(resp_json: Dict) -> Optional[str]:
    """
    Robust extractor to pull generated text from various Gemini response shapes.
    Common path: candidates[0].content.parts[0].text
    Alternate: output -> content -> parts
    Fallback: deep search for the first 'text' string.
    """
    try:
        candidates = resp_json.get("candidates")
        if isinstance(candidates, list) and candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts and isinstance(parts[0], dict) and "text" in parts[0]:
                return parts[0]["text"].strip()
    except Exception:
        pass

    # Alternate path
    try:
        output = resp_json.get("output")
        if isinstance(output, list):
            for entry in output:
                c = entry.get("content", [])
                if isinstance(c, list):
                    for item in c:
                        parts = item.get("parts") or []
                        if parts and isinstance(parts[0], dict) and "text" in parts[0]:
                            return parts[0]["text"].strip()
    except Exception:
        pass

    # Deep fallback
    def deep_find(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "text" and isinstance(v, str):
                    return v.strip()
                res = deep_find(v)
                if res:
                    return res
        elif isinstance(o, list):
            for e in o:
                res = deep_find(e)
                if res:
                    return res
        return None

    return deep_find(resp_json)

def _strip_code_fence(s: str) -> str:
    if s.startswith("```"):
        parts = s.split("\n", 1)
        if len(parts) > 1:
            return parts[1].rsplit("\n", 1)[0]
    return s

def _next_weekday_date(meeting_date: str, weekday_name: str) -> Optional[str]:
    """
    Given meeting_date 'YYYY-MM-DD' and weekday name like 'Friday',
    return next occurrence date as 'YYYY-MM-DD'. If meeting_date parse fails, return None.
    """
    try:
        days = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
        base = datetime.strptime(meeting_date, "%Y-%m-%d").date()
        target = days.get(weekday_name.lower())
        if target is None:
            return None
        delta_days = (target - base.weekday() + 7) % 7
        if delta_days == 0:
            delta_days = 7
        return (base + timedelta(days=delta_days)).isoformat()
    except Exception:
        return None

# ---------------------- Gemini call wrapper ---------------------- #
def _call_gemini(system_text: str, user_text: str, temperature: float = 0.0, max_output_tokens: int = 800, candidate_count: int = 1) -> Dict:
    """
    Call the Generative Language API. We send a labelled system instruction as the
    first 'user' content (because the model accepts only role 'user' or 'model').
    """
    system_as_user_part = {
        "role": "user",
        "parts": [
            {"text": system_text}
        ]
    }
    user_part = {
        "role": "user",
        "parts": [
            {"text": user_text}
        ]
    }

    payload = {
        "contents": [system_as_user_part, user_part],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "candidateCount": candidate_count
        }
    }

    try:
        resp = requests.post(GEMINI_URL, headers=HEADERS, json=payload, timeout=30)
    except Exception as e:
        raise RuntimeError(f"Request to Gemini failed: {e}")

    if not resp.ok:
        # show full body to help debugging
        body = None
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise RuntimeError(f"Gemini API returned HTTP {resp.status_code}. Response body:\n{json.dumps(body, indent=2) if isinstance(body, dict) else body}")

    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to decode Gemini JSON response: {e}\nRaw: {resp.text[:2000]}")

# ---------------------- Main extractor function ---------------------- #
def extract_mom_actions(transcript: str, attendees: List[Dict], meeting_date: str, max_retries: int = 2) -> Dict:
    """
    Extracts M.O.M and actions from transcript.
    - transcript: raw meeting transcript (string)
    - attendees: list of {"name": <str>, "email": <str>}
    - meeting_date: "YYYY-MM-DD"
    Returns a dict matching the requested schema.
    Retries with slightly stricter system instruction if model returns non-JSON.
    """
    attendee_names = [a["name"] for a in attendees]
    user_prompt_text = (
        f"Meeting Date: {meeting_date}\n"
        f"Attendees: {', '.join(attendee_names)}\n\n"
        f"Transcript:\n{transcript[:3500]}"
    )

    attempt = 0
    current_system_text = SYSTEM_INSTRUCTION_TEXT

    while attempt <= max_retries:
        attempt += 1
        resp_json = _call_gemini(current_system_text, user_prompt_text, temperature=0.0, max_output_tokens=1000, candidate_count=1)
        generated = _find_generated_text(resp_json)

        if not generated:
            if attempt <= max_retries:
                current_system_text = SYSTEM_INSTRUCTION_TEXT + "\nIMPORTANT: Output ONLY raw JSON. DO NOT include any text outside the JSON."
                continue
            raise RuntimeError(f"No text found in model response (attempt {attempt}). Full response keys: {list(resp_json.keys())}")

        generated = _strip_code_fence(generated)

        # Try parse
        try:
            data = json.loads(generated)
        except json.JSONDecodeError as e:
            # If model explicitly returned the special invalid_response sentinel, treat as failure to parse and retry
            if attempt <= max_retries:
                current_system_text = SYSTEM_INSTRUCTION_TEXT + "\nCRITICAL: If you cannot output valid JSON, return exactly {\"error\":\"invalid_response\"} and nothing else."
                continue
            # final failure: include truncated model output to help debugging
            raise ValueError(f"Failed to JSON-decode model output (attempt {attempt}): {e}\nModel output (truncated):\n{generated[:1500]}")

        # Normalize fields
        if "mom" not in data:
            data.setdefault("mom", "")
        if "actions" not in data or not isinstance(data["actions"], list):
            data["actions"] = []

        # enrich actions
        for act in data.get("actions", []):
            # owner email enrichment
            owner = (act.get("owner") or "UNASSIGNED").strip()
            matched = next((a for a in attendees if a["name"] in owner), None)
            act["owner_email"] = matched["email"] if matched else "unassigned@company.com"

            # deadline normalization if weekday string
            dl = act.get("deadline")
            if isinstance(dl, str) and dl.lower() in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday"):
                nd = _next_weekday_date(meeting_date, dl)
                act["deadline"] = nd if nd else None

            # priority normalization
            pr = (act.get("priority") or "").lower()
            act["priority"] = pr if pr in ("high","medium","low") else "medium"

        return data

    raise RuntimeError("Extractor failed unexpectedly")

# ---------------------- CLI/test convenience ---------------------- #
if __name__ == "__main__":
    # quick smoke test (does call the API)
    sample_transcript = (
        "Alice: I'll update the spec by Friday.\n"
        "Bob: I'll review it next Monday.\n"
        "Carol: No actions from me."
    )
    attendees = [
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "Bob", "email": "bob@example.com"},
        {"name": "Carol", "email": "carol@example.com"},
    ]
    meeting_date = datetime.utcnow().date().isoformat()
    print("Calling Gemini (model: {})...".format(GEMINI_MODEL))
    try:
        result = extract_mom_actions(sample_transcript, attendees, meeting_date)
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print("Error running extractor:", exc)
