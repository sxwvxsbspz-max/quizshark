#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ElevenLabs v3 Quizmaster TTS (SoundMemory)
- liest questions.json im SoundMemory-Format:
  [
    { "image_id": "song_0004", ..., "questions": [ { "id": 1, "question": "...", ... }, ... ] },
    ...
  ]
- erzeugt pro Frage eine MP3 im bestehenden Audio-Ordner:
    question-<image_id>-<question_id>.mp3
  z.B. question-song_0004-1.mp3
- schreibt pro Frage questions[].audio auf diesen Dateinamen
- v3 Handling:
  - Prefix: [confident] [energetic]
  - Fragezeichen am Satzende entfernen
  - Punkt / Ellipsis setzen
- API-Key aus /11labsapi.json (Projekt-Root)
- Postprocessing gegen "abgehackt":
  - hängt Stille ans Ende (PAD_SECONDS)
  - optional: kleines Fade-out am Ende (FADE_SECONDS)
  -> benötigt ffmpeg + ffprobe
- NEU: Protokoll:
  - loggt: erzeugt / übersprungen + Grund / Fehler
  - loggt: JSON-Updates
  - loggt: wie viele MP3 im Ordner liegen (am Ende)
  - schreibt in soundmemory/11labsprotokoll.txt

Datei:
  soundmemory/elevenlabsv3.py
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Projekt-Root (eine Ebene über dem Modulordner)
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

API_JSON_PATH = os.path.join(PROJECT_ROOT, "11labsapi.json")

# questions.json im selben Ordner wie dieses Script
QUESTIONS_JSON = os.path.join(BASE_DIR, "questions.json")

# WICHTIG: Audio muss in media/audio liegen, damit dein Programm es findet
AUDIO_DIR = os.path.join(BASE_DIR, "media", "audio")

# Protokoll-Datei
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
USE_ELLIPSIS_FOR_SHORT = True
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

    # Regie-Tags nur einmal
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

    af = ",".join(filters) if filters else "anull"

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
        raise ValueError("Leerer Text")

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

    if os.path.exists(tmp_dl):
        os.remove(tmp_dl)


def safe_filename(s: str) -> str:
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


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
    append_log(f"[{now_stamp()}] START elevenlabsv3.py (SoundMemory)")
    append_log(f"Audio-Ordner: {AUDIO_DIR}")
    append_log(f"Questions:     {QUESTIONS_JSON}")
    append_log(f"FORCE_REGEN:   {FORCE_REGENERATE}")
    append_log(f"Voice:         {VOICE_ID} | Model: {MODEL_ID} | Stability: {V3_STABILITY}")
    append_log("============================================================")

    with open(QUESTIONS_JSON, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not isinstance(items, list):
        raise RuntimeError("questions.json hat nicht das erwartete Array-Format (Liste von Songs).")

    print("🎙️ Generiere SoundMemory Question-Audio (Leon Stern · v3 Quizmaster)")

    changed = False
    produced = 0
    skipped = 0
    failed = 0
    json_updates = 0
    total_questions_seen = 0

    for song_idx, song in enumerate(items, start=1):
        image_id = (song.get("image_id") or "").strip()
        questions = song.get("questions") or []

        if not image_id:
            skipped += 1
            append_log(f"[SKIP] song_idx={song_idx} -> image_id fehlt/leer")
            continue

        if not isinstance(questions, list):
            skipped += 1
            append_log(f"[SKIP] song_idx={song_idx} image_id={image_id} -> questions ist keine Liste")
            continue

        image_id_safe = safe_filename(image_id)

        for q in questions:
            qid = q.get("id")
            text = (q.get("question") or "").strip()

            total_questions_seen += 1

            if qid is None:
                skipped += 1
                append_log(f"[SKIP] image_id={image_id_safe} id=None -> keine id im JSON")
                continue

            if not text:
                skipped += 1
                append_log(f"[SKIP] image_id={image_id_safe} id={qid} -> question leer")
                continue

            # Schema: question-<image_id>-<question_id>.mp3 (IMMER in media/audio)
            audio_name = f"question-{image_id_safe}-{qid}.mp3"
            out_path = os.path.join(AUDIO_DIR, audio_name)

            # JSON aktualisieren
            if (q.get("audio") or "").strip() != audio_name:
                q["audio"] = audio_name
                changed = True
                json_updates += 1
                append_log(f"[JSON] image_id={image_id_safe} id={qid} audio gesetzt -> {audio_name}")

            # Existiert schon?
            if (not FORCE_REGENERATE) and os.path.exists(out_path):
                skipped += 1
                append_log(f"[SKIP] image_id={image_id_safe} id={qid} -> existiert bereits ({audio_name})")
                continue

            print(f"[{image_id_safe}:{qid}] {audio_name}")
            append_log(f"[GEN ] image_id={image_id_safe} id={qid} -> {audio_name}")

            try:
                generate_audio(text, out_path)
                produced += 1
                append_log(f"[OK  ] image_id={image_id_safe} id={qid} -> erzeugt")
                time.sleep(0.35)
            except Exception as e:
                failed += 1
                append_log(f"[ERR ] image_id={image_id_safe} id={qid} -> {e}")

    if changed:
        atomic_write(QUESTIONS_JSON, items)

    total_mp3 = count_mp3_files(AUDIO_DIR)

    append_log("------------------------------------------------------------")
    append_log(f"[{now_stamp()}] ENDE")
    append_log(f"fragen gesehen: {total_questions_seen}")
    append_log(f"produziert:    {produced}")
    append_log(f"übersprungen:  {skipped}")
    append_log(f"fehler:        {failed}")
    append_log(f"json-updates:  {json_updates}")
    append_log(f"mp3 im Ordner: {total_mp3}")
    append_log("============================================================")

    print("✅ Fertig.")
    print(f"📄 Protokoll: {PROTOCOL_PATH}")
    print(f"📦 MP3 im Ordner: {total_mp3}")


if __name__ == "__main__":
    main()
