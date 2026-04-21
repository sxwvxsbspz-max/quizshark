#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================
# sortquestions.py
#
# Zweck:
# - mischt die Fragen in questions.json zufällig
# - nummeriert die IDs anschließend neu (0001..N)
# - benennt zugehörige MP3-Dateien entsprechend um (question-<id>.mp3)
# - aktualisiert die Audio-Einträge in der JSON
#
# Sicherheitslogik:
# - prüft VORHER:
#     * jede in JSON referenzierte MP3 existiert
#     * keine MP3 wird von mehreren Fragen referenziert
#     * keine zusätzliche MP3 im Audio-Ordner ohne JSON-Eintrag existiert
# - wenn ein Problem gefunden wird -> ABBRUCH, nichts wird geändert
#
# Ablauf:
# 1. Vorprüfung der Konsistenz zwischen JSON und Audio-Ordner
# 2. Backup der questions.json
# 3. Fragen zufällig mischen
# 4. IDs neu vergeben (4-stellig: 0001, 0002, ...)
# 5. Audio-Dateien in zwei Phasen sicher umbenennen
# 6. JSON speichern
# 7. Nachprüfung durchführen
#
# Logging:
# - vollständiges Protokoll in sortquestions_protokoll.txt
# - enthält Prüfungen, Rename-Plan und Ergebnis
#
# Voraussetzungen:
# - Script liegt im gleichen Ordner wie questions.json
# - Audio-Dateien liegen in ./media/audio/
#
# Start:
#   python3 sortquestions.py
# ============================================================

import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = BASE_DIR / "questions.json"
AUDIO_DIR = BASE_DIR / "media" / "audio"

BACKUP_JSON_FILE = BASE_DIR / "questions.backup.json"
LOG_FILE = BASE_DIR / "sortquestions_protokoll.txt"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_questions(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("questions.json enthält keine Liste.")
    return data


def save_questions(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_log(lines):
    with LOG_FILE.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def normalize_audio_name(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value:
        return ""
    if "/" in value or "\\" in value:
        raise ValueError(f"Ungültiger Audio-Dateiname mit Pfadanteil: {value}")
    return value


def is_mp3_file(path: Path):
    return path.is_file() and path.suffix.lower() == ".mp3"


def collect_json_audio_refs(questions):
    refs = []
    for idx, q in enumerate(questions, start=1):
        audio = normalize_audio_name(q.get("audio", ""))
        refs.append({
            "json_index": idx,
            "id": q.get("id"),
            "question": q.get("question", ""),
            "audio": audio
        })
    return refs


def validate_before_start(questions, log_lines):
    errors = []
    warnings = []

    if not QUESTIONS_FILE.exists():
        errors.append(f"questions.json nicht gefunden: {QUESTIONS_FILE}")

    if not AUDIO_DIR.exists():
        errors.append(f"Audio-Ordner nicht gefunden: {AUDIO_DIR}")

    if errors:
        return errors, warnings

    json_refs = collect_json_audio_refs(questions)

    referenced_audio = [r for r in json_refs if r["audio"]]
    referenced_names = [r["audio"] for r in referenced_audio]

    seen = {}
    for r in referenced_audio:
        seen.setdefault(r["audio"], []).append(r)

    for audio_name, entries in seen.items():
        if len(entries) > 1:
            details = " | ".join(
                f"id={e['id']}, json_index={e['json_index']}, frage={e['question']}"
                for e in entries
            )
            errors.append(
                f"Doppelte Audio-Referenz in JSON: {audio_name} -> {details}"
            )

    for r in referenced_audio:
        p = AUDIO_DIR / r["audio"]
        if not p.exists():
            errors.append(
                f"Referenzierte Audio-Datei fehlt: {r['audio']} "
                f"(id={r['id']}, frage={r['question']})"
            )
        elif not is_mp3_file(p):
            errors.append(
                f"Referenzierte Datei ist keine MP3: {r['audio']} "
                f"(id={r['id']}, frage={r['question']})"
            )

    existing_mp3s = sorted([p.name for p in AUDIO_DIR.iterdir() if is_mp3_file(p)])
    referenced_set = set(referenced_names)
    existing_set = set(existing_mp3s)

    orphan_files = sorted(existing_set - referenced_set)
    for name in orphan_files:
        errors.append(f"MP3-Datei ohne JSON-Eintrag gefunden: {name}")

    for r in json_refs:
        if not r["audio"]:
            warnings.append(
                f"Frage ohne Audio-Eintrag: id={r['id']}, json_index={r['json_index']}, frage={r['question']}"
            )

    log_lines.append("=== VORPRÜFUNG ===")
    if warnings:
        for w in warnings:
            log_lines.append(f"[INFO] {w}")
    if errors:
        for e in errors:
            log_lines.append(f"[FEHLER] {e}")
    else:
        log_lines.append("[OK] Vorprüfung erfolgreich. Keine Inkonsistenzen gefunden.")

    return errors, warnings


def validate_after_finish(questions, log_lines):
    errors = []

    json_refs = collect_json_audio_refs(questions)

    seen = {}
    for r in json_refs:
        if not r["audio"]:
            continue
        seen.setdefault(r["audio"], []).append(r)

        p = AUDIO_DIR / r["audio"]
        if not p.exists():
            errors.append(
                f"Nachprüfung: referenzierte Datei fehlt: {r['audio']} "
                f"(id={r['id']}, frage={r['question']})"
            )
        elif not is_mp3_file(p):
            errors.append(
                f"Nachprüfung: referenzierte Datei ist keine MP3: {r['audio']} "
                f"(id={r['id']}, frage={r['question']})"
            )

    for audio_name, entries in seen.items():
        if len(entries) > 1:
            details = " | ".join(
                f"id={e['id']}, json_index={e['json_index']}, frage={e['question']}"
                for e in entries
            )
            errors.append(
                f"Nachprüfung: doppelte Audio-Referenz: {audio_name} -> {details}"
            )

    existing_mp3s = sorted([p.name for p in AUDIO_DIR.iterdir() if is_mp3_file(p)])
    referenced_set = {r["audio"] for r in json_refs if r["audio"]}
    existing_set = set(existing_mp3s)

    orphan_files = sorted(existing_set - referenced_set)
    for name in orphan_files:
        errors.append(f"Nachprüfung: MP3-Datei ohne JSON-Eintrag gefunden: {name}")

    log_lines.append("")
    log_lines.append("=== NACHPRÜFUNG ===")
    if errors:
        for e in errors:
            log_lines.append(f"[FEHLER] {e}")
    else:
        log_lines.append("[OK] Nachprüfung erfolgreich. JSON und Audio-Dateien sind konsistent.")

    return errors


def rollback_temp_files(temp_moves, log_lines):
    log_lines.append("")
    log_lines.append("=== ROLLBACK ===")
    for tmp_path, original_path in reversed(temp_moves):
        try:
            if tmp_path.exists():
                tmp_path.rename(original_path)
                log_lines.append(f"[OK] Rollback: {tmp_path.name} -> {original_path.name}")
        except Exception as e:
            log_lines.append(f"[FEHLER] Rollback fehlgeschlagen: {tmp_path} -> {original_path} | {e}")


def main():
    log_lines = [
        "SORTQUESTIONS PROTOKOLL",
        f"Zeitpunkt: {now_iso()}",
        f"Script: {Path(__file__).name}",
        f"Questions: {QUESTIONS_FILE}",
        f"Audio-Ordner: {AUDIO_DIR}",
        ""
    ]

    try:
        questions = load_questions(QUESTIONS_FILE)
    except Exception as e:
        log_lines.append(f"[FEHLER] Konnte questions.json nicht laden: {e}")
        write_log(log_lines)
        print("FEHLER. Details im Protokoll.")
        sys.exit(1)

    errors, _warnings = validate_before_start(questions, log_lines)
    if errors:
        log_lines.append("")
        log_lines.append("ABBRUCH: Es wurden vor dem Start Fehler gefunden. Es wurde nichts geändert.")
        write_log(log_lines)
        print("Abbruch. Details im Protokoll.")
        sys.exit(1)

    shutil.copy2(QUESTIONS_FILE, BACKUP_JSON_FILE)
    log_lines.append("")
    log_lines.append("=== BACKUP ===")
    log_lines.append(f"[OK] Backup erstellt: {BACKUP_JSON_FILE}")

    random.shuffle(questions)

    log_lines.append("")
    log_lines.append("=== UMBENENNUNGSPLAN ===")

    rename_jobs = []
    for new_id, q in enumerate(questions, start=1):
        old_id = q.get("id")
        old_audio = normalize_audio_name(q.get("audio", ""))
        question = q.get("question", "")

        q["id"] = f"{new_id:04d}"

        if old_audio:
            new_audio = f"question-{new_id}.mp3"
            q["audio"] = new_audio
            rename_jobs.append({
                "old_id": old_id,
                "new_id": f"{new_id:04d}",
                "old_audio": old_audio,
                "new_audio": new_audio,
                "question": question
            })
            log_lines.append(
                f"[PLAN] alt ID {old_id} -> neu ID {new_id:04d} | "
                f"{old_audio} -> {new_audio} | Frage: {question}"
            )
        else:
            q["audio"] = ""
            log_lines.append(
                f"[PLAN] alt ID {old_id} -> neu ID {new_id:04d} | "
                f"ohne Audio | Frage: {question}"
            )

    source_names = {j["old_audio"] for j in rename_jobs}
    target_names = {j["new_audio"] for j in rename_jobs}

    for target_name in sorted(target_names):
        target_path = AUDIO_DIR / target_name
        if target_path.exists() and target_name not in source_names:
            log_lines.append(
                f"[FEHLER] Zieldatei würde überschrieben und ist nicht Teil der Quellen: {target_name}"
            )
            log_lines.append("ABBRUCH: Es wurde nichts an JSON oder Audio gespeichert.")
            write_log(log_lines)
            print("Abbruch. Details im Protokoll.")
            sys.exit(1)

    temp_moves = []
    try:
        log_lines.append("")
        log_lines.append("=== PHASE 1: TEMP-RENAME ===")
        for job in rename_jobs:
            src = AUDIO_DIR / job["old_audio"]
            tmp = AUDIO_DIR / f"__tmp__sortquestions__oldid_{job['old_id']}__{job['old_audio']}"
            src.rename(tmp)
            temp_moves.append((tmp, src))
            log_lines.append(f"[OK] TEMP {job['old_audio']} -> {tmp.name}")

        log_lines.append("")
        log_lines.append("=== PHASE 2: FINAL-RENAME ===")
        for job in rename_jobs:
            tmp = AUDIO_DIR / f"__tmp__sortquestions__oldid_{job['old_id']}__{job['old_audio']}"
            dst = AUDIO_DIR / job["new_audio"]
            tmp.rename(dst)
            log_lines.append(f"[OK] FINAL {tmp.name} -> {job['new_audio']}")

    except Exception as e:
        log_lines.append("")
        log_lines.append(f"[FEHLER] Umbenennung fehlgeschlagen: {e}")
        rollback_temp_files(temp_moves, log_lines)
        log_lines.append("")
        log_lines.append("ABBRUCH: Audio-Dateien wurden per Rollback zurückgesetzt. JSON wurde nicht gespeichert.")
        write_log(log_lines)
        print("FEHLER beim Umbenennen. Details im Protokoll.")
        sys.exit(1)

    try:
        save_questions(QUESTIONS_FILE, questions)
        log_lines.append("")
        log_lines.append("=== JSON SPEICHERN ===")
        log_lines.append(f"[OK] questions.json gespeichert: {QUESTIONS_FILE}")
    except Exception as e:
        log_lines.append("")
        log_lines.append(f"[FEHLER] Konnte questions.json nicht speichern: {e}")
        log_lines.append("HINWEIS: Audio-Dateien wurden bereits umbenannt. Backup der alten JSON liegt vor.")
        write_log(log_lines)
        print("FEHLER beim JSON-Speichern. Details im Protokoll.")
        sys.exit(1)

    post_errors = validate_after_finish(questions, log_lines)
    if post_errors:
        log_lines.append("")
        log_lines.append("ABSCHLUSS MIT FEHLERN: Sortierung wurde durchgeführt, aber die Nachprüfung ist fehlgeschlagen.")
        write_log(log_lines)
        print("Fertig, aber Nachprüfung fehlgeschlagen. Details im Protokoll.")
        sys.exit(1)

    log_lines.append("")
    log_lines.append("=== ABSCHLUSS ===")
    log_lines.append("[OK] Sortierung, Umbenennung und Prüfungen erfolgreich abgeschlossen.")
    write_log(log_lines)

    print("Fertig.")
    print(f"questions.json aktualisiert: {QUESTIONS_FILE}")
    print(f"Backup erstellt: {BACKUP_JSON_FILE}")
    print(f"Protokoll geschrieben: {LOG_FILE}")


if __name__ == "__main__":
    main()