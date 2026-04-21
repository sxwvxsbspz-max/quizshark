#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ElevenLabs v3 Quizmaster TTS (Punktesammler)
- liest questions.json
- erzeugt MP3s in ./media/audio
- Naming: <id>.mp3
- v3 Handling:
  - Prefix: [confident] [energetic]
  - Fragezeichen am Satzende entfernen
  - Punkt / Ellipsis setzen
- API-Key aus /11labsapi.json (Projekt-Root)
- Postprocessing gegen "abgehackt":
  - hängt Stille ans Ende (PAD_SECONDS)
  - optional: kleines Fade-out am Ende (FADE_SECONDS)
- NEU: Protokoll:
  - loggt: erzeugt / übersprungen + Grund / Fehler
  - loggt: wie viele Audios im Ordner liegen (am Ende)
  - schreibt in punktesammler/11labsprotokoll.txt

Datei:
  punktesammler/elevenlabsv3.py
"""

import os
import json
import time
import subprocess
from datetime import datetime
import requests

# =========================================================
# PFADE
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))           # .../punktesammler
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))    # .../blitzquiz

API_JSON_PATH = os.path.join(PROJECT_ROOT, "11labsapi.json")
QUESTIONS_JSON = os.path.join(BASE_DIR, "questions.json")
AUDIO_DIR = os.path.join(BASE_DIR, "media", "audio")
PROTOCOL_PATH = os.path.join(BASE_DIR, "11labsprotokoll.txt")

# =========================================================
# API KEY LADEN
# =========================================================

if not os.path.exists(API_JSON_PATH):
    raise RuntimeError(f"11labsapi.json nicht gefunden: {API_JSON_PATH}")

with open(API_JSON_PATH, "r", encoding="utf-8") as f:
    api_cfg = json.load(f)

API_KEY = (api_cfg.get("api_key") or "").strip()
if not API_KEY:
    raise RuntimeError("api_key fehlt/leer in 11labsapi.json")

# =========================================================
# ELEVENLABS SETTINGS (v3)
# =========================================================

VOICE_ID = "re2r5d74PqDzicySNW0I"   # Leon Stern
MODEL_ID = "eleven_v3"
OUTPUT_FORMAT = "mp3_44100_192"

# v3: stability nur 0.0 / 0.5 / 1.0
V3_STABILITY = 0.5  # 0.0=Creative, 0.5=Natural, 1.0=Robust

VOICE_SETTINGS = {
    "stability": V3_STABILITY
}

TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

# =========================================================
# QUIZMASTER PREPROCESSING
# =========================================================

QUIZ_PREFIX = "[confident] [energetic] "
USE_ELLIPSIS_FOR_SHORT = False
SHORT_QUESTION_THRESHOLD = 45

FORCE_REGENERATE = False

# =========================================================
# AUDIO POSTPROCESSING
# =========================================================

PAD_SECONDS = 0.70
FADE_SECONDS = 0.25
USE_FADE_OUT = True

# =========================================================
# HELPERS
# =========================================================

def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_log(line: str):
    with open(PROTOCOL_PATH, "a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def normalize_quizmaster_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""

    t = " ".join(t.split())

    # Upspeak vermeiden -> Fragezeichen durch Punkt ersetzen
    if t.endswith("?"):
        t = t[:-1].rstrip() + "."

    # Satzende absichern
    if not t.endswith((".", "!", "…")):
        if USE_ELLIPSIS_FOR_SHORT and len(t) <= SHORT_QUESTION_THRESHOLD:
            t += "..."
        else:
            t += "."

    # Regie nur einmal
    if not t.startswith("["):
        t = QUIZ_PREFIX + t

    return t


def _run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()


def get_audio_duration_seconds(path: str) -> float:
    out = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ])
    return float(out)


def pad_and_fade_mp3(in_path: str, out_path: str):
    dur = get_audio_duration_seconds(in_path)

    filters = []
    if USE_FADE_OUT and dur > FADE_SECONDS:
        fade_start = max(0.0, dur - FADE_SECONDS)
        filters.append(f"afade=t=out:st={fade_start}:d={FADE_SECONDS}")

    if PAD_SECONDS > 0:
        filters.append(f"apad=pad_dur={PAD_SECONDS}")

    af = ",".join(filters)

    _run([
        "ffmpeg", "-y",
        "-i", in_path,
        "-af", af,
        "-c:a", "libmp3lame",
        "-q:a", "3",
        out_path
    ])


def generate_audio(text: str, out_path: str):
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    prepared_text = normalize_quizmaster_text(text)
    if not prepared_text:
        raise ValueError("Leerer Text nach Preprocessing")

    params = {"output_format": OUTPUT_FORMAT}

    payload = {
        "text": prepared_text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS
    }

    r = requests.post(
        TTS_URL,
        headers=headers,
        json=payload,
        params=params,
        timeout=120
    )

    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs Fehler {r.status_code}: {r.text}")

    tmp_dl = out_path + ".tmp_dl.mp3"
    tmp_final = out_path + ".tmp_final.mp3"

    with open(tmp_dl, "wb") as f:
        f.write(r.content)

    pad_and_fade_mp3(tmp_dl, tmp_final)
    os.replace(tmp_final, out_path)
    os.remove(tmp_dl)


def count_mp3_files(folder: str) -> int:
    if not os.path.isdir(folder):
        return 0
    return sum(1 for fn in os.listdir(folder) if fn.lower().endswith(".mp3"))


# =========================================================
# MAIN
# =========================================================

def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)

    append_log("")
    append_log("============================================================")
    append_log(f"[{now_stamp()}] START elevenlabsv3.py (Punktesammler)")
    append_log(f"Audio-Ordner: {AUDIO_DIR}")
    append_log(f"Questions:     {QUESTIONS_JSON}")
    append_log(f"FORCE_REGEN:   {FORCE_REGENERATE}")
    append_log(f"Voice:         {VOICE_ID} | Model: {MODEL_ID} | Stability: {V3_STABILITY}")
    append_log("============================================================")

    with open(QUESTIONS_JSON, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print("🎙️ Generiere Quiz-Audio (Leon Stern · v3 Quizmaster)")

    produced = 0
    skipped = 0
    failed = 0
    updated_json = 0

    for idx, q in enumerate(questions, start=1):
        qid = q.get("id")
        text = (q.get("question") or "").strip()

        if qid is None:
            skipped += 1
            append_log(f"[SKIP] idx={idx} id=None -> keine id im JSON")
            continue

        if not text:
            skipped += 1
            append_log(f"[SKIP] idx={idx} id={qid} -> question leer")
            continue

        audio_name = f"{qid}.mp3"
        out_path = os.path.join(AUDIO_DIR, audio_name)

        if (q.get("audio") or "").strip() != audio_name:
            q["audio"] = audio_name
            atomic_write(QUESTIONS_JSON, questions)
            updated_json += 1
            append_log(f"[JSON] idx={idx} id={qid} audio gesetzt -> {audio_name}")

        if (not FORCE_REGENERATE) and os.path.exists(out_path):
            skipped += 1
            append_log(f"[SKIP] idx={idx} id={qid} -> existiert bereits ({audio_name})")
            continue

        print(f"[{idx}] {audio_name}")
        append_log(f"[GEN ] idx={idx} id={qid} -> {audio_name}")

        try:
            generate_audio(text, out_path)
            produced += 1
            append_log(f"[OK  ] idx={idx} id={qid} -> erzeugt")
            time.sleep(0.35)
        except Exception as e:
            failed += 1
            append_log(f"[ERR ] idx={idx} id={qid} -> {e}")
            continue

    total_mp3 = count_mp3_files(AUDIO_DIR)

    append_log("------------------------------------------------------------")
    append_log(f"[{now_stamp()}] ENDE")
    append_log(f"produziert:   {produced}")
    append_log(f"übersprungen: {skipped}")
    append_log(f"fehler:       {failed}")
    append_log(f"json-updates: {updated_json}")
    append_log(f"mp3 im Ordner:{total_mp3}")
    append_log("============================================================")

    print("✅ Fertig.")
    print(f"📄 Protokoll: {PROTOCOL_PATH}")
    print(f"📦 MP3 im Ordner: {total_mp3}")


if __name__ == "__main__":
    main()
