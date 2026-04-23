#!/usr/bin/env python3
"""
Generates categoryannouncement1-N.mp3 files via ElevenLabs.
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
    1:  "Die nächste Kategorie ist?-",
    2:  "Jetzt spielen wir eine Frage zu?-",
    3:  "Das nächste Thema lautet?-",
    4:  "Die nächste Frage kommt aus dem Bereich?-",
    5:  "Aufgepasst, wir spielen jetzt?-",
    6:  "Das nächste Thema ist?-",
    7:  "Bereitet euch vor auf?-",
    8:  "Die folgende Kategorie steht auf dem Plan?-",
    9:  "Jetzt kommt eine Frage aus dem Bereich?-",
    10: "Aufgepasst! Das Thema lautet?-",
    11: "Wir widmen uns jetzt dem Thema?-",
    12: "Nächste Kategorie?-",
    13: "Die nächste Frage dreht sich um?-",
    14: "Jetzt geht es um?-",
    15: "Das nächste Wissensgebiet ist?-",
    16: "Achtung, neue Kategorie?-",
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
    print(f"  Generating categoryannouncement{num}.mp3 — \"{text}\" ...")
    r = requests.post(url, json=body, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return False
    os.makedirs(_OUT_DIR, exist_ok=True)
    out = os.path.join(_OUT_DIR, f"categoryannouncement{num}.mp3")
    with open(out, "wb") as f:
        f.write(r.content)
    print(f"  Saved → {out}")
    return True

if __name__ == "__main__":
    for num, text in TEXTS.items():
        generate(num, text)
    print("Done.")
