#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ElevenLabs Jahres-Ansagen für Songster TV
- Erzeugt year-<jahr>.mp3 in ./media/gamesounds/
- Leon Stern · eleven_v3
- API-Key aus /11labsapi.json (Projekt-Root)
- Überspringt bereits vorhandene Dateien
"""

import os
import json
import time
import subprocess
import requests

# =========================================================
# PFADE
# =========================================================

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

API_JSON_PATH = os.path.join(PROJECT_ROOT, "11labsapi.json")
AUDIO_DIR     = os.path.join(BASE_DIR, "media", "gamesounds")

# =========================================================
# TEXTE
# =========================================================

YEAR_TEXTS = {
    1930: "Dieser Song stammt aus dem Jahr 1930!",
    1931: "Dieser Song kommt aus dem Jahr 1931!",
    1932: "Dieser Song stammt aus dem Jahr 1932!",
    1933: "Dieser Hit kommt aus dem Jahr 1933!",
    1934: "Dieser Song kommt aus dem Jahr 1934!",
    1935: "Jahrgang 1935!",
    1936: "Das war Musik aus dem Jahr 1936!",
    1937: "Dieser Titel erschien 1937!",
    1938: "Ein Klassiker aus dem Jahr 1938!",
    1939: "Dieser Song stammt aus dem Jahr 1939!",
    1940: "Ein Song aus dem Jahr 1940!",
    1941: "Dieser Titel stammt aus dem Jahr 1941!",
    1942: "Dieser Song kommt aus dem Jahr 1942!",
    1943: "Ein Hit aus dem Jahr 1943!",
    1944: "Dieser Song erschien 1944!",
    1945: "Jahrgang 1945!",
    1946: "Das war Musik aus dem Jahr 1946!",
    1947: "Dieser Song stammt aus dem Jahr 1947!",
    1948: "Dieser Song kommt aus dem Jahr 1948!",
    1949: "Ein Klassiker aus dem Jahr 1949!",
    1950: "Dieser Song kommt aus dem Jahr 1950!",
    1951: "Ein Song aus dem Jahr 1951!",
    1952: "Dieser Song stammt aus dem Jahr 1952!",
    1953: "Dieser Titel erschien 1953!",
    1954: "Ein Hit aus dem Jahr 1954!",
    1955: "Jahrgang 1955!",
    1956: "Das war Musik aus dem Jahr 1956!",
    1957: "Ein Song aus dem Jahr 1957!",
    1958: "Dieser Titel kommt aus dem Jahr 1958!",
    1959: "Ein Klassiker aus dem Jahr 1959!",
    1960: "Das hier ist aus dem Jahr 1960!",
    1961: "Ein Song aus dem Jahr 1961!",
    1962: "Wir schreiben das Jahr 1962!",
    1963: "Dieser Hit stammt aus dem Jahr 1963!",
    1964: "Ein Titel aus dem Jahr 1964!",
    1965: "Jahrgang 1965!",
    1966: "Das war Musik aus dem Jahr 1966!",
    1967: "Ein Song aus dem Jahr 1967!",
    1968: "Dieser Titel erschien 1968!",
    1969: "Ein Klassiker aus dem Jahr 1969!",
    1970: "Dieser Song kommt aus dem Jahr 1970!",
    1971: "Ein Titel aus dem Jahr 1971!",
    1972: "Wir schreiben das Jahr 1972!",
    1973: "Dieser Hit stammt aus dem Jahr 1973!",
    1974: "Ein Song aus dem Jahr 1974!",
    1975: "Jahrgang 1975!",
    1976: "Das war Musik aus dem Jahr 1976!",
    1977: "Ein Titel aus dem Jahr 1977!",
    1978: "Dieser Song erschien 1978!",
    1979: "Ein Klassiker aus dem Jahr 1979!",
    1980: "Das hier stammt aus dem Jahr 1980!",
    1981: "Ein Song aus dem Jahr 1981!",
    1982: "Wir schreiben das Jahr 1982!",
    1983: "Dieser Hit kommt aus dem Jahr 1983!",
    1984: "Ein Titel aus dem Jahr 1984!",
    1985: "Jahrgang 1985!",
    1986: "Das war Musik aus dem Jahr 1986!",
    1987: "Ein Song aus dem Jahr 1987!",
    1988: "Dieser Titel erschien 1988!",
    1989: "Ein Klassiker aus dem Jahr 1989!",
    1990: "Dieser Song stammt aus dem Jahr 1990!",
    1991: "Ein Titel aus dem Jahr 1991!",
    1992: "Wir schreiben das Jahr 1992!",
    1993: "Dieser Hit kommt aus dem Jahr 1993!",
    1994: "Ein Song aus dem Jahr 1994!",
    1995: "Jahrgang 1995!",
    1996: "Das war Musik aus dem Jahr 1996!",
    1997: "Ein Titel aus dem Jahr 1997!",
    1998: "Dieser Song erschien 1998!",
    1999: "Ein Klassiker aus dem Jahr 1999!",
    2000: "Das hier ist aus dem Jahr 2000!",
    2001: "Ein Song aus dem Jahr 2001!",
    2002: "Wir schreiben das Jahr 2002!",
    2003: "Dieser Hit stammt aus dem Jahr 2003!",
    2004: "Ein Titel aus dem Jahr 2004!",
    2005: "Jahrgang 2005!",
    2006: "Das war Musik aus dem Jahr 2006!",
    2007: "Ein Song aus dem Jahr 2007!",
    2008: "Dieser Titel erschien 2008!",
    2009: "Ein Klassiker aus dem Jahr 2009!",
    2010: "Dieser Song kommt aus dem Jahr 2010!",
    2011: "Ein Titel aus dem Jahr 2011!",
    2012: "Wir schreiben das Jahr 2012!",
    2013: "Dieser Hit stammt aus dem Jahr 2013!",
    2014: "Ein Song aus dem Jahr 2014!",
    2015: "Jahrgang 2015!",
    2016: "Das war Musik aus dem Jahr 2016!",
    2017: "Ein Titel aus dem Jahr 2017!",
    2018: "Dieser Song erschien 2018!",
    2019: "Dieser Song kommt aus dem Jahr 2019!",
    2020: "Das hier stammt aus dem Jahr 2020!",
    2021: "Ein Song aus dem Jahr 2021!",
    2022: "Wir schreiben das Jahr 2022!",
    2023: "Dieser Hit kommt aus dem Jahr 2023!",
    2024: "Ein Titel aus dem Jahr 2024!",
    2025: "Jahrgang 2025!",
    2026: "Das war Musik aus dem Jahr 2026!",
    2027: "Ein Song aus dem Jahr 2027!",
    2028: "Dieser Titel erscheint 2028!",
    2029: "Ein Track aus dem Jahr 2029!",
    2030: "Musik aus dem Jahr 2030!",
}

# =========================================================
# ELEVENLABS SETTINGS
# =========================================================

VOICE_ID      = "re2r5d74PqDzicySNW0I"   # Leon Stern
MODEL_ID      = "eleven_v3"
OUTPUT_FORMAT = "mp3_44100_192"
V3_STABILITY  = 0.5

TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

# =========================================================
# AUDIO POSTPROCESSING
# =========================================================

PAD_SECONDS  = 0.70
FADE_SECONDS = 0.25
USE_FADE_OUT = True

# =========================================================
# HELPERS
# =========================================================

def _run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()


def get_duration(path):
    out = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ])
    return float(out)


def pad_and_fade(in_path, out_path):
    dur = get_duration(in_path)
    filters = []
    if USE_FADE_OUT and dur > FADE_SECONDS:
        filters.append(f"afade=t=out:st={max(0.0, dur - FADE_SECONDS)}:d={FADE_SECONDS}")
    if PAD_SECONDS > 0:
        filters.append(f"apad=pad_dur={PAD_SECONDS}")
    _run([
        "ffmpeg", "-y", "-i", in_path,
        "-af", ",".join(filters),
        "-c:a", "libmp3lame", "-q:a", "3",
        out_path
    ])


def generate_audio(text, out_path, api_key):
    prepared = f"[confident] [energetic] {text}"

    r = requests.post(
        TTS_URL,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": prepared, "model_id": MODEL_ID, "voice_settings": {"stability": V3_STABILITY}},
        params={"output_format": OUTPUT_FORMAT},
        timeout=120
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")

    tmp_dl    = out_path + ".tmp_dl.mp3"
    tmp_final = out_path + ".tmp_final.mp3"
    with open(tmp_dl, "wb") as f:
        f.write(r.content)
    pad_and_fade(tmp_dl, tmp_final)
    os.replace(tmp_final, out_path)
    os.remove(tmp_dl)


# =========================================================
# MAIN
# =========================================================

def main():
    if not os.path.exists(API_JSON_PATH):
        raise RuntimeError(f"11labsapi.json nicht gefunden: {API_JSON_PATH}")
    with open(API_JSON_PATH, "r", encoding="utf-8") as f:
        api_key = json.load(f).get("api_key", "").strip()
    if not api_key:
        raise RuntimeError("api_key fehlt in 11labsapi.json")

    os.makedirs(AUDIO_DIR, exist_ok=True)

    years = sorted(YEAR_TEXTS.keys())
    total = len(years)
    produced = skipped = failed = 0

    print(f"🎙️  Jahres-Ansagen · Leon Stern · {total} Jahre")

    for year in years:
        filename = f"year-{year}.mp3"
        out_path = os.path.join(AUDIO_DIR, filename)

        if os.path.exists(out_path):
            skipped += 1
            print(f"  [SKIP] {filename}")
            continue

        text = YEAR_TEXTS[year]
        print(f"  [GEN ] {filename}  →  {text}")
        try:
            generate_audio(text, out_path, api_key)
            produced += 1
            time.sleep(0.35)
        except Exception as e:
            failed += 1
            print(f"  [ERR ] {filename}: {e}")

    print(f"\n✅ Fertig — erzeugt: {produced}, übersprungen: {skipped}, fehler: {failed}")


if __name__ == "__main__":
    main()
