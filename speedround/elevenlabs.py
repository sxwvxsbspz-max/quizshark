#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import requests

# =========================
# KONFIGURATION
# =========================
API_KEY  = "sk_b89a2abaf8a2ed1122f4e4b4f3377b797a0a5feb22f45eba"
VOICE_ID = "re2r5d74PqDzicySNW0I"
MODEL_ID = "eleven_multilingual_v2"
OUTPUT_FORMAT = "mp3_44100_192"

# 🎛️ EMPFEHLUNG A – natürlich, kein Blech
VOICE_SETTINGS = {
    "stability": 0.65,
    "similarity_boost": 0.75,
    "style": 0.20,
    "use_speaker_boost": False
}

# WICHTIG:
# - False = nur generieren, wenn Datei fehlt (empfohlen, spart Credits)
# - True  = immer neu generieren
FORCE_REGENERATE = False

# =========================
# PFADE & URL
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_JSON = os.path.join(BASE_DIR, "questions.json")
AUDIO_DIR = os.path.join(BASE_DIR, "media", "audio")
TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def generate_clean_quiz_audio(text: str, out_path: str):
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    prepared_text = text.strip()
    if not prepared_text.endswith((".", "!", "?")):
        prepared_text += "."

    params = {
        "optimize_streaming_latency": 0,
        "output_format": OUTPUT_FORMAT
    }

    payload = {
        "text": prepared_text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS
    }

    response = requests.post(
        TTS_URL,
        headers=headers,
        json=payload,
        params=params,
        timeout=120
    )

    if response.status_code != 200:
        raise RuntimeError(f"Fehler {response.status_code}: {response.text}")

    with open(out_path, "wb") as f:
        f.write(response.content)

def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)

    with open(QUESTIONS_JSON, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print("🎙️ Generiere Quiz-Audio...")

    for i, q in enumerate(questions, start=1):
        qid = q.get("id")
        text = (q.get("question") or "").strip()
        if qid is None or not text:
            continue

        # ==========================================================
        # GEWÜNSCHTE LOGIK
        # 1) Wenn JSON 'audio' hat:
        #    - prüfe, ob genau diese Datei existiert
        #    - wenn fehlt: neu erzeugen (Name bleibt)
        # 2) Wenn JSON 'audio' fehlt/leer:
        #    - setze standardisierten Namen (0001.mp3 ...)
        #    - schreibe JSON sofort
        #    - wenn Datei fehlt: erzeugen
        # ==========================================================
        audio_in_json = (q.get("audio") or "").strip()

        if audio_in_json:
            filename = audio_in_json
        else:
            filename = f"{qid:04d}.mp3"  # 0001.mp3, 0002.mp3, ...
            q["audio"] = filename
            atomic_write(QUESTIONS_JSON, questions)  # sofort persistieren

        out_path = os.path.join(AUDIO_DIR, filename)

        if FORCE_REGENERATE or not os.path.exists(out_path):
            print(f"[{i}] Audio: {filename}")
            try:
                generate_clean_quiz_audio(text, out_path)
                time.sleep(0.5)
            except Exception as e:
                print(f"Fehler bei {filename}: {e}")
                continue

        # Wenn audio in JSON vorhanden war, aber z.B. Whitespace / Abweichung, sauber setzen
        if q.get("audio") != filename:
            q["audio"] = filename
            atomic_write(QUESTIONS_JSON, questions)

    print("\n✅ Fertig.")

if __name__ == "__main__":
    main()
