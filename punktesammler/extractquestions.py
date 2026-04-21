#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
punktesammler/extractquestions.py

Liest punktesammler/questions.json und schreibt eine Protokolldatei mit:
ID | Frage

Output:
  punktesammler/extractquestions.txt
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, List, Dict


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_JSON = os.path.join(SCRIPT_DIR, "questions.json")
OUT_TXT = os.path.join(SCRIPT_DIR, "extractquestions.txt")


def _load_json_fallback(path: str) -> Any:
    """
    Robust laden:
    - Normal: json.load(file)
    - Fallback: Datei als Text lesen und json.loads()
      (hilft, falls z.B. unsichtbare BOM/Whitespace oder ein JSON-String drin ist)
    """
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            f.seek(0)
            raw = f.read().strip()

    # Falls jemand das JSON als String abgespeichert hat: " [ ... ] "
    # -> einmal ent-quoten und nochmal versuchen
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Versuch: wenn es mit Anführungszeichen beginnt/endet, abziehen
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw2 = raw[1:-1].strip()
            # ggf. escaped newlines/quotes entschärfen
            raw2 = raw2.replace(r"\n", "\n").replace(r"\"","\"").replace(r"\'","'")
            return json.loads(raw2)
        raise


def _ensure_list(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data  # type: ignore[return-value]
    if isinstance(data, dict):
        # Häufige Varianten: {"questions":[...]} oder {"data":[...]}
        for key in ("questions", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]  # type: ignore[return-value]
    raise ValueError("questions.json hat kein erwartetes Format (Array oder dict mit questions/data/items).")


def _norm_id(v: Any) -> str:
    # IDs sind bei dir Strings wie "00005". Falls mal int drin ist: auf 5 Stellen zero-pad.
    if v is None:
        return ""
    if isinstance(v, int):
        return f"{v:05d}"
    s = str(v).strip()
    # Wenn es rein numerisch ist und keine führenden Nullen hat, auf 5 Stellen bringen
    if s.isdigit() and len(s) < 5:
        s = s.zfill(5)
    return s


def main() -> int:
    if not os.path.exists(QUESTIONS_JSON):
        print(f"FEHLER: Nicht gefunden: {QUESTIONS_JSON}", file=sys.stderr)
        return 2

    try:
        data = _load_json_fallback(QUESTIONS_JSON)
        items = _ensure_list(data)
    except Exception as e:
        print(f"FEHLER beim Laden/Parsen von {QUESTIONS_JSON}: {e}", file=sys.stderr)
        return 3

    lines: List[str] = []
    skipped = 0

    for i, obj in enumerate(items, start=1):
        if not isinstance(obj, dict):
            skipped += 1
            continue

        qid = _norm_id(obj.get("id"))
        question = obj.get("question")

        if question is None:
            skipped += 1
            continue

        q = str(question).strip().replace("\r\n", "\n").replace("\r", "\n")
        # sicherstellen: eine Zeile pro Eintrag
        q = " ".join(q.splitlines()).strip()

        if not qid or not q:
            skipped += 1
            continue

        lines.append(f"{qid} | {q}")

    # Datei schreiben (überschreibt)
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    with open(OUT_TXT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")

    print(f"OK: {len(lines)} Zeilen geschrieben -> {OUT_TXT}")
    if skipped:
        print(f"Hinweis: {skipped} Einträge übersprungen (fehlende/ungültige id oder question).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
