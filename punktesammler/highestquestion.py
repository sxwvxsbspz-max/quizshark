#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "questions.json")


def main():
    if not os.path.exists(JSON_PATH):
        print(f"Fehler: Datei nicht gefunden: {JSON_PATH}")
        sys.exit(1)

    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Fehler beim Lesen der JSON: {e}")
        sys.exit(1)

    if not isinstance(data, list):
        print("Fehler: questions.json muss ein JSON-Array sein.")
        sys.exit(1)

    valid_ids = []
    invalid_ids = []
    seen = set()
    duplicates = set()

    for i, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            invalid_ids.append(f"Eintrag #{i}: kein Objekt")
            continue

        raw_id = entry.get("id", None)

        if raw_id is None:
            invalid_ids.append(f"Eintrag #{i}: keine id vorhanden")
            continue

        if not isinstance(raw_id, str):
            invalid_ids.append(f"Eintrag #{i}: id ist nicht vom Typ String ({raw_id})")
            continue

        if not raw_id.isdigit():
            invalid_ids.append(f"Eintrag #{i}: ungültige id '{raw_id}'")
            continue

        num_id = int(raw_id)
        valid_ids.append(num_id)

        if num_id in seen:
            duplicates.add(num_id)
        else:
            seen.add(num_id)

    if not valid_ids:
        print("Keine gültigen IDs gefunden.")
        if invalid_ids:
            print("\nUngültige Einträge:")
            for item in invalid_ids:
                print(f"- {item}")
        sys.exit(1)

    max_id = max(valid_ids)
    max_id_str = str(max_id).zfill(5)

    existing_ids = set(valid_ids)
    full_range = set(range(1, max_id + 1))
    missing_ids = sorted(full_range - existing_ids)
    duplicates_sorted = sorted(duplicates)

    print("=== Ergebnis ===")
    print(f"Höchste ID: {max_id_str} (numerisch: {max_id})")
    print(f"Anzahl gültiger ID-Einträge: {len(valid_ids)}")

    if not missing_ids:
        print(f"Alle Fragen von 00001 bis {max_id_str} sind vorhanden: JA")
    else:
        print(f"Alle Fragen von 00001 bis {max_id_str} sind vorhanden: NEIN")
        print(f"Fehlende IDs: {len(missing_ids)}")
        print(", ".join(str(x).zfill(5) for x in missing_ids))

    if duplicates_sorted:
        print(f"Doppelte IDs gefunden: {len(duplicates_sorted)}")
        print(", ".join(str(x).zfill(5) for x in duplicates_sorted))
    else:
        print("Doppelte IDs gefunden: keine")

    if invalid_ids:
        print(f"Ungültige Einträge gefunden: {len(invalid_ids)}")
        for item in invalid_ids:
            print(f"- {item}")
    else:
        print("Ungültige Einträge gefunden: keine")


if __name__ == "__main__":
    main()