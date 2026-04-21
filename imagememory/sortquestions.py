#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILE = BASE / "questions.json"

with open(FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

image_ids = [item["image_id"] for item in data]

print("Vorhandene image_ids:")
for i in image_ids:
    print(i)

data_sorted = sorted(data, key=lambda x: x["image_id"])

with open(FILE, "w", encoding="utf-8") as f:
    json.dump(data_sorted, f, indent=4, ensure_ascii=False)

print("\nSortierung abgeschlossen.")