# --- FILE: ./lobby/generate_player_audio_files.py ---
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Player-Name -> ElevenLabs MP3 Generator (Best-Effort, Join-safe)

Ziel:
- Prüft playerdata/playersounds/map.json auf Eintrag für den normalisierten Namen-Key
  (Normalisierung MUSS zur leaderboard/tv.html normalizeName() passen)
- Wenn kein Eintrag existiert:
    -> erzeugt MP3 via ElevenLabs
    -> speichert unter playerdata/playersounds/<key>.mp3
    -> aktualisiert map.json atomisch + Backup
- Wenn Eintrag existiert, aber MP3 fehlt:
    -> erzeugt MP3 unter dem gemappten Dateinamen
    -> map.json bleibt wie es ist

WICHTIG:
- Fehlerresistent: niemals Exceptions nach außen werfen (Join darf NIE scheitern)
- Concurrency-safe: File-Lock + atomisches Schreiben + Backup
- Optionales Audio-Postprocessing (Pad + Fade) nur wenn ffmpeg/ffprobe vorhanden ist
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

# File locking (Linux/macOS)
try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))           # .../lobby
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))    # .../blitzquiz (repo root)

PLAYER_SOUNDS_DIR = os.path.join(PROJECT_ROOT, "playerdata", "playersounds")
MAP_PATH = os.path.join(PLAYER_SOUNDS_DIR, "map.json")
MAP_BAK_PATH = os.path.join(PLAYER_SOUNDS_DIR, "map.json.bak")
LOCK_PATH = os.path.join(PLAYER_SOUNDS_DIR, "map.lock")
LOG_PATH = os.path.join(PLAYER_SOUNDS_DIR, "generate.log")

API_JSON_PATH = os.path.join(PROJECT_ROOT, "11labsapi.json")


# =========================================================
# ELEVENLABS SETTINGS (v3)
# =========================================================

DEFAULT_VOICE_ID = "re2r5d74PqDzicySNW0I"  # Leon Stern
MODEL_ID = "eleven_v3"
OUTPUT_FORMAT = "mp3_44100_192"

# v3: stability nur 0.0 / 0.5 / 1.0
V3_STABILITY = 0.5

VOICE_SETTINGS = {
    "stability": V3_STABILITY
}

# Join-safe timeouts (kurz!)
HTTP_TIMEOUT = (5, 18)  # (connect, read) seconds

# Optional: "cooldown" nach Fehlern, um bei API-down nicht zu spammen
_COOLDOWN_UNTIL_TS = 0.0
COOLDOWN_SECONDS_ON_FAIL = 45.0

# Lock acquisition policy
LOCK_TRY_SECONDS = 0.35
LOCK_SLEEP_STEP = 0.03


# =========================================================
# AUDIO POSTPROCESSING (optional)
# =========================================================

PAD_SECONDS = 0.55
FADE_SECONDS = 0.20
USE_FADE_OUT = True


# =========================================================
# LOGGING
# =========================================================

def _log(line: str) -> None:
    try:
        os.makedirs(PLAYER_SOUNDS_DIR, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {line.rstrip()}\n")
    except Exception:
        # niemals crashen wegen logging
        pass


# =========================================================
# NORMALIZATION (MUSS leaderboard/tv.html entsprechen)
# =========================================================

def normalize_player_sound_key(name: str) -> str:
    """
    Spiegelung der JS normalizeName() aus leaderboard/tv.html:
    - trim + lower
    - NUR erstes Wort (alles nach erstem Leerzeichen weg)
    - Umlaute: ä->ae, ö->oe, ü->ue, ß->ss
    - andere Diakritika entfernen (é->e)
    - nur a-z0-9 behalten
    """
    s = str(name or "").strip().lower()

    if " " in s:
        s = s.split(" ")[0]

    s = (
        s.replace("ä", "ae")
         .replace("ö", "oe")
         .replace("ü", "ue")
         .replace("ß", "ss")
    )

    # andere Diakritika entfernen
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

    # nur a-z0-9
    s = re.sub(r"[^a-z0-9]", "", s)

    return s


def _first_word_for_tts(original_name: str) -> str:
    s = str(original_name or "").strip()
    if not s:
        return ""
    # wie frontend: erstes Wort ist das, was am Ende "entscheidet"
    return s.split()[0]


# =========================================================
# JSON IO (atomic + backup)
# =========================================================

def _safe_load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _atomic_backup_map_if_exists() -> None:
    """
    Legt/aktualisiert map.json.bak atomisch, falls map.json existiert.
    """
    try:
        if not os.path.exists(MAP_PATH):
            return
        # map.json lesen (falls kaputt -> backup trotzdem nicht überschreiben)
        current = _safe_load_json(MAP_PATH)
        if current is None:
            return

        tmp = MAP_BAK_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        os.replace(tmp, MAP_BAK_PATH)
    except Exception:
        # Backup darf niemals Join blockieren
        pass


# =========================================================
# LOCKING
# =========================================================

@dataclass
class _FileLock:
    fp: Any

    def release(self) -> None:
        try:
            if fcntl is not None:
                fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            self.fp.close()
        except Exception:
            pass


def _try_acquire_lock() -> Optional[_FileLock]:
    """
    Nicht blockierend mit kurzem Retry-Fenster.
    Wenn nicht erreichbar -> None (skip; Audio ist optional).
    """
    if fcntl is None:
        # Ohne fcntl kein echter Prozess-Lock -> wir skippen lieber, statt Risiko "zerhackt"
        _log("LOCK: fcntl nicht verfügbar -> skip")
        return None

    os.makedirs(PLAYER_SOUNDS_DIR, exist_ok=True)
    start = time.time()
    fp = None

    try:
        fp = open(LOCK_PATH, "a+", encoding="utf-8")
        while True:
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return _FileLock(fp=fp)
            except BlockingIOError:
                if (time.time() - start) >= LOCK_TRY_SECONDS:
                    try:
                        fp.close()
                    except Exception:
                        pass
                    return None
                time.sleep(LOCK_SLEEP_STEP)
    except Exception:
        try:
            if fp:
                fp.close()
        except Exception:
            pass
        return None


# =========================================================
# ELEVENLABS API
# =========================================================

def _load_api_key() -> Optional[str]:
    cfg = _safe_load_json(API_JSON_PATH)
    if not cfg:
        return None
    key = str(cfg.get("api_key") or "").strip()
    return key or None


def _normalize_tts_text(spoken_word: str) -> str:
    """
    Playername-TTS: kurz, stabil, kein Fragezeichen.
    """
    t = str(spoken_word or "").strip()
    t = " ".join(t.split())
    if not t:
        return ""
    if t.endswith("?"):
        t = t[:-1].rstrip()
    if not t.endswith((".", "!", "…")):
        t += "."
    # leichte Regie, nicht zu aggressiv
    if not t.startswith("["):
        t = f"(euphorisch) {t}!"
    return t


def _run(cmd: list[str]) -> str:
    import subprocess
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "command failed")
    return p.stdout.strip()


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _get_audio_duration_seconds(path: str) -> float:
    out = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ])
    return float(out)


def _pad_and_fade_mp3(in_path: str, out_path: str) -> None:
    dur = _get_audio_duration_seconds(in_path)

    filters: list[str] = []
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


def _download_tts_mp3(text: str, out_path: str, *, voice_id: str) -> None:
    api_key = _load_api_key()
    if not api_key:
        raise RuntimeError("missing_api_key")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    params = {"output_format": OUTPUT_FORMAT}
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
    }

    r = requests.post(url, headers=headers, json=payload, params=params, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"elevenlabs_status_{r.status_code}")

    tmp_dl = out_path + ".tmp_dl.mp3"
    tmp_final = out_path + ".tmp_final.mp3"

    with open(tmp_dl, "wb") as f:
        f.write(r.content)

    # Optional postprocess gegen "abgehackt"
    if _ffmpeg_available():
        try:
            _pad_and_fade_mp3(tmp_dl, tmp_final)
            os.replace(tmp_final, out_path)
            try:
                os.remove(tmp_dl)
            except Exception:
                pass
            return
        except Exception as e:
            # ffmpeg kaputt? -> fallback: raw mp3
            _log(f"FFMPEG: fallback raw ({e})")

    os.replace(tmp_dl, out_path)
    try:
        if os.path.exists(tmp_final):
            os.remove(tmp_final)
    except Exception:
        pass


# =========================================================
# PUBLIC API
# =========================================================

def ensure_player_sound(name: str, *, voice_id: str = DEFAULT_VOICE_ID) -> Dict[str, Any]:
    """
    Best-effort ensure, dass für den Spielernamen ein map.json Eintrag + MP3 existiert.

    Rückgabe (nur für Logs/Debug, Caller kann ignorieren):
    - { ok: True, action: 'exists'|'generated'|'regenerated_missing_file'|'skipped_*', key, filename }
    - { ok: False, action: 'skipped_*', key?, error }
    """
    global _COOLDOWN_UNTIL_TS

    try:
        # Cooldown nach Fail: gar nicht erst versuchen
        now = time.time()
        if now < float(_COOLDOWN_UNTIL_TS or 0.0):
            return {"ok": False, "action": "skipped_cooldown", "error": "cooldown_active"}

        os.makedirs(PLAYER_SOUNDS_DIR, exist_ok=True)

        spoken = _first_word_for_tts(name)
        key = normalize_player_sound_key(name)

        if not key:
            return {"ok": False, "action": "skipped_invalid_key", "error": "empty_key"}

        # Lock holen (wenn busy -> skip)
        lock = _try_acquire_lock()
        if lock is None:
            return {"ok": False, "action": "skipped_lock_busy", "key": key, "error": "lock_busy"}

        try:
            # Map laden (map.json -> bak -> {})
            m = _safe_load_json(MAP_PATH)
            if m is None:
                m = _safe_load_json(MAP_BAK_PATH) or {}

            # Double-check (wichtig bei Concurrency)
            mapped_filename = str(m.get(key) or "").strip() if isinstance(m, dict) else ""
            if mapped_filename:
                target_filename = mapped_filename
                target_path = os.path.join(PLAYER_SOUNDS_DIR, target_filename)

                if os.path.exists(target_path):
                    return {"ok": True, "action": "exists", "key": key, "filename": target_filename}

                # Map sagt: existiert, File fehlt -> regenerieren unter gemapptem Namen
                tts_text = _normalize_tts_text(spoken or key)
                if not tts_text:
                    return {"ok": False, "action": "skipped_empty_tts_text", "key": key, "error": "empty_tts_text"}

                _log(f"SOUND: regen missing file key={key} -> {target_filename}")
                _download_tts_mp3(tts_text, target_path, voice_id=voice_id)

                if os.path.exists(target_path):
                    return {"ok": True, "action": "regenerated_missing_file", "key": key, "filename": target_filename}

                return {"ok": False, "action": "failed_regenerate", "key": key, "error": "file_not_written"}

            # Kein Mapping -> generieren in <key>.mp3 und map updaten
            target_filename = f"{key}.mp3"
            target_path = os.path.join(PLAYER_SOUNDS_DIR, target_filename)

            # Falls File schon existiert (manuell), nur Mapping ergänzen
            if os.path.exists(target_path):
                # Backup + atomic map write
                if not isinstance(m, dict):
                    m = {}
                m[key] = target_filename
                _atomic_backup_map_if_exists()
                _atomic_write_json(MAP_PATH, m)
                _log(f"SOUND: map-only key={key} -> {target_filename}")
                return {"ok": True, "action": "mapped_existing_file", "key": key, "filename": target_filename}

            # Generieren
            tts_text = _normalize_tts_text(spoken or key)
            if not tts_text:
                return {"ok": False, "action": "skipped_empty_tts_text", "key": key, "error": "empty_tts_text"}

            _log(f"SOUND: gen key={key} -> {target_filename}")
            _download_tts_mp3(tts_text, target_path, voice_id=voice_id)

            if not os.path.exists(target_path):
                return {"ok": False, "action": "failed_generate", "key": key, "error": "file_not_written"}

            # Map updaten (Backup + atomic)
            if not isinstance(m, dict):
                m = {}
            m[key] = target_filename
            _atomic_backup_map_if_exists()
            _atomic_write_json(MAP_PATH, m)

            return {"ok": True, "action": "generated", "key": key, "filename": target_filename}

        finally:
            try:
                lock.release()
            except Exception:
                pass

    except Exception as e:
        # Fail fast + cooldown, niemals join blocken
        _log(f"SOUND: FAIL ({type(e).__name__}) {e}")
        try:
            _COOLDOWN_UNTIL_TS = time.time() + COOLDOWN_SECONDS_ON_FAIL
        except Exception:
            pass
        return {"ok": False, "action": "failed_exception", "error": f"{type(e).__name__}"}


# Convenience alias (falls du den Namen lieber so willst)
ensure_player_sound_for_name = ensure_player_sound
