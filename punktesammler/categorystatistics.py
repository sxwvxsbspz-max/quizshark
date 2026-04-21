#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Category Statistics für BlitzQuiz / Punktesammler

- Liest punktesammler/questions.json
- Zählt Fragen je "category"
- Gibt absolute + prozentuale Anteile aus
- Gibt Gesamtanzahl aus
- Schreibt ein Protokoll nach punktesammler/categorystatistics.txt
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter


DEFAULT_JSON_PATH = Path("punktesammler") / "questions.json"
DEFAULT_LOG_PATH = Path("punktesammler") / "categorystatistics.txt"


def load_questions(json_path: Path) -> list[dict]:
    if not json_path.exists():
        raise FileNotFoundError(f"JSON nicht gefunden: {json_path.resolve()}")

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Ungültiges Format: Root-Element muss eine Liste sein (Array).")

    return data


def normalize_category(cat) -> str:
    if cat is None:
        return "(ohne Kategorie)"
    if not isinstance(cat, str):
        return "(ungültige Kategorie)"
    cat = cat.strip()
    return cat if cat else "(ohne Kategorie)"


def make_report(questions: list[dict], json_path: Path) -> str:
    total = len(questions)
    counter = Counter()

    for q in questions:
        if isinstance(q, dict):
            counter[normalize_category(q.get("category"))] += 1
        else:
            counter["(ungültiger Eintrag)"] += 1

    # Sortierung: zuerst nach Anzahl (desc), dann alphabetisch
    rows = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))

    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    lines = []
    lines.append("=== Category Statistics (Punktesammler) ===")
    lines.append(f"Zeit (UTC): {now}")
    lines.append(f"Quelle: {json_path.resolve()}")
    lines.append("")
    lines.append(f"Gesamtanzahl Fragen: {total}")
    lines.append("")
    lines.append("Kategorie | Anzahl | Anteil")
    lines.append("-" * 60)

    if total == 0:
        lines.append("(Keine Fragen gefunden)")
    else:
        for cat, count in rows:
            pct = (count / total) * 100.0
            lines.append(f"{cat} | {count} | {pct:6.2f}%")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    json_path = DEFAULT_JSON_PATH
    log_path = DEFAULT_LOG_PATH

    try:
        questions = load_questions(json_path)
        report = make_report(questions, json_path)

        # Log-Verzeichnis sicherstellen
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # In Datei schreiben (überschreibt bewusst, damit es “der aktuelle Stand” ist)
        with log_path.open("w", encoding="utf-8") as f:
            f.write(report)

        # Zusätzlich in die Konsole (praktisch beim manuellen Run)
        print(report)
        print(f"Protokoll geschrieben: {log_path.resolve()}")
        return 0

    except Exception as e:
        err = f"[ERROR] {e}"
        print(err)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write("\n" + "=" * 60 + "\n")
                f.write(datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") + "\n")
                f.write(err + "\n")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
