#!/usr/bin/env python3
"""
Generates categoryfrom1-N.mp3 files via ElevenLabs.
Output goes to yourcategory/media/gamesounds/
"""

import json, os, sys, requests

_ROOT        = os.path.dirname(os.path.abspath(__file__))
_KEY_PATH    = os.path.join(_ROOT, "11labsapi.json")
_OUT_DIR     = os.path.join(_ROOT, "yourcategory", "media", "gamesounds")

_VOICE_ID      = "re2r5d74PqDzicySNW0I"
_MODEL_ID      = "eleven_v3"
_OUTPUT_FORMAT = "mp3_44100_192"
_TTS_PREFIX    = "[confident] [energetic] "

TEXTS = {
    1:  "Diese Kategorie wurde ausgesucht von?-",
    2:  "Ausgesucht hat diese Kategorie?-",
    3:  "Für diese Kategorie verantwortlich ist?-",
    4:  "Diese Kategorie geht auf das Konto von?-",
    5:  "Diese Kategorie wurde euch beschert von?-",
    6:  "Schuld an dieser Kategorie ist?-",
    7:  "Diese Kategorie kommt von?-",
    8:  "Die Kategorie wurde gewählt von?-",
    9:  "Diese Kategorie ist ein Geschenk von?-",
    10: "Diese Themenwahl lag in den Händen von?-",
    11: "Diese Kategorie stammt aus dem Kopf von?-",
    12: "Diese Kategorie wurde mit Bedacht gewählt von?-",
    13: "Hinter dieser Kategorie steckt?-",
    14: "Diese Kategorie wurde liebevoll ausgewählt von?-",
}

def _api_key():
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if k:
        return k
    with open(_KEY_PATH, "r", encoding="utf-8") as f:
        return (json.load(f).get("api_key") or "").strip()

def generate(num: int, text: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{_VOICE_ID}?output_format={_OUTPUT_FORMAT}"
    headers = {
        "xi-api-key": _api_key(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": f"{_TTS_PREFIX}{text}",
        "model_id": _MODEL_ID,
        "voice_settings": {"stability": 0.5},
    }
    print(f"  Generating categoryfrom{num}.mp3 — \"{text}\" ...")
    r = requests.post(url, json=body, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return False
    os.makedirs(_OUT_DIR, exist_ok=True)
    out = os.path.join(_OUT_DIR, f"categoryfrom{num}.mp3")
    with open(out, "wb") as f:
        f.write(r.content)
    print(f"  Saved → {out}")
    return True

if __name__ == "__main__":
    for num, text in TEXTS.items():
        out = os.path.join(_OUT_DIR, f"categoryfrom{num}.mp3")
        if os.path.exists(out):
            print(f"  Skipping categoryfrom{num}.mp3 (already exists)")
            continue
        generate(num, text)
    print("Done.")
