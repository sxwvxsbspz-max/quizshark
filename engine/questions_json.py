# --- FILE: ./engine/questions_json.py ---

import json
import os
from datetime import datetime, timezone


def now_iso_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json_questions(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_questions(path: str, questions):
    # atomic-ish write
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)


def lastplayed_ts(q: dict) -> float:
    lp = q.get("lastplayed")
    if not lp:
        return 0.0
    try:
        return datetime.fromisoformat(lp.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0