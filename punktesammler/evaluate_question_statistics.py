# --- FILE: ./punktesammler/stats_questions.py ---
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


def _load_questions(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("questions.json muss ein JSON-Array (Liste) sein.")
    return data


def _parse_lastplayed(value: Any) -> Optional[datetime]:
    """
    Erwartet typischerweise ISO-Strings wie:
      - "2026-01-23T15:40:27Z"
      - "2026-01-23T15:40:27+00:00"
    Gibt None zurück bei leer/ungültig.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None

    # Häufig: ...Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # fromisoformat versteht "+00:00", aber nicht zwingend alle Varianten.
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        # Fallback: ein paar bekannte Formate
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            return None

    # timezone-naiv -> als UTC interpretieren (konservativ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def _build_report(questions: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    total = len(questions)

    played = 0
    unplayed = 0

    by_day = Counter()  # YYYY-MM-DD -> count
    invalid_lastplayed = 0

    # Optional: Top-Kategorien nach gespielt/nicht gespielt
    played_by_cat = Counter()
    unplayed_by_cat = Counter()

    for q in questions:
        lp_raw = q.get("lastplayed", "")
        cat = str(q.get("category", "Unbekannt")).strip() or "Unbekannt"
        dt = _parse_lastplayed(lp_raw)

        if dt is None:
            # leere lastplayed -> unplayed
            if isinstance(lp_raw, str) and lp_raw.strip() == "":
                unplayed += 1
                unplayed_by_cat[cat] += 1
            else:
                # irgendwas drin, aber nicht parsebar -> zählt als "gespielt (ungültig)"? besser getrennt
                invalid_lastplayed += 1
        else:
            played += 1
            played_by_cat[cat] += 1
            day = dt.date().isoformat()
            by_day[day] += 1

    # Wenn lastplayed ungültig war: behandeln wir diese als "gespielt?", aber getrennt ausweisen
    # (du kannst es später leicht ändern, falls du sie zu played zählen willst)
    accounted = played + unplayed + invalid_lastplayed

    # Report-Text bauen
    lines = []
    lines.append("Punktesammler – questions.json Statistik")
    lines.append("=" * 45)
    lines.append(f"Gesamt:                 {total}")
    lines.append(f"Gespielt (parsebar):    {played}")
    lines.append(f"Nicht gespielt (leer):  {unplayed}")
    lines.append(f"Ungültig lastplayed:    {invalid_lastplayed}")
    lines.append(f"Summe geprüft:          {accounted}")
    if accounted != total:
        lines.append(f"⚠️ Hinweis: {total - accounted} Einträge konnten nicht sauber ausgewertet werden (unerwartete Struktur).")
    lines.append("")

    # Tagesübersicht
    lines.append("Letztes Spielen pro Datum (YYYY-MM-DD)")
    lines.append("-" * 45)
    if by_day:
        for day, cnt in sorted(by_day.items()):
            lines.append(f"{day}: {cnt}")
    else:
        lines.append("(Keine parsebaren lastplayed-Daten gefunden)")
    lines.append("")

    # Kategorieübersicht (Top 15)
    def _format_top(counter: Counter, title: str, top_n: int = 15):
        lines.append(title)
        lines.append("-" * 45)
        if not counter:
            lines.append("(keine Daten)")
        else:
            for k, v in counter.most_common(top_n):
                lines.append(f"{k}: {v}")
        lines.append("")

    _format_top(played_by_cat, "Top Kategorien (gespielt)")
    _format_top(unplayed_by_cat, "Top Kategorien (nicht gespielt)")

    # Metadaten-Objekt (falls du später JSON-Output willst)
    meta = {
        "total": total,
        "played_parseable": played,
        "unplayed_empty": unplayed,
        "invalid_lastplayed": invalid_lastplayed,
        "by_day": dict(sorted(by_day.items())),
        "played_by_category_top": played_by_cat.most_common(50),
        "unplayed_by_category_top": unplayed_by_cat.most_common(50),
    }

    return "\n".join(lines), meta


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    questions_path = base_dir / "questions.json"  # RELATIV: gleicher Ordner
    if not questions_path.exists():
        print(f"FEHLER: questions.json nicht gefunden unter: {questions_path.name} (relativ zum Skript).")
        return 1

    try:
        questions = _load_questions(questions_path)
    except Exception as e:
        print(f"FEHLER beim Laden von questions.json: {e}")
        return 2

    report_text, _meta = _build_report(questions)

    # Konsole
    print(report_text)

    # Protokolldatei (relativ im gleichen Ordner)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = base_dir / f"questions_stats_{ts}.txt"
    try:
        log_path.write_text(report_text, encoding="utf-8")
        print(f"\nProtokoll geschrieben: {log_path.name}")
    except Exception as e:
        print(f"\nWARNUNG: Konnte Protokolldatei nicht schreiben: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
