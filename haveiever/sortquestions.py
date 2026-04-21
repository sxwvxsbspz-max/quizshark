# --- FILE: ./haveiever/sortquestions.py ---
"""
Mischt haveiever/questions.json zufällig, nummeriert IDs neu von 00001..xxxxx,
benennt zugehörige Audio-Dateien in ./haveiever/media/audio passend um
und schreibt ein detailliertes Protokoll.

WICHTIG: 3 Phasen (hart, sorgfältig)

PHASE 1 (Vorbereitung / nur prüfen):
- Ordner existiert
- Für jeden gesetzten JSON-Audio-Eintrag (pre_audio/audio) existiert die Datei (sonst: meckern + abbrechen)
- Umgekehrt: Es gibt keine Audio-Dateien (pre_audio_*.mp3 / question_*.mp3) im Ordner, die NICHT im JSON referenziert sind
  (sonst: meckern + abbrechen)
- Naming-Logik muss passen:
  - pre_audio: "pre_audio_<id>.mp3"
  - audio:     "question_<id>.mp3"
  - und die ID in der Datei muss zur Frage-ID passen
- Danach: Shuffle + neues Mapping + Rename-Plan erstellen
- Plan validieren (keine Zielkollisionen, keine Overwrites außerhalb des Plans)

PHASE 2 (Umbenennen):
- zweistufig: SOURCE -> TMP, TMP -> TARGET (swap-safe)

PHASE 3 (Check):
- JSON + Dateien konsistent
- keine TMP-Dateien übrig
- wieder "beidseitiger" Check (JSON->Dateien und Dateien->JSON)

Usage:
  python3 haveiever/sortquestions.py
  python3 haveiever/sortquestions.py --seed 123
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(HERE, "questions.json")
MEDIA_AUDIO_DIR = os.path.join(HERE, "media", "audio")
LOG_PATH = os.path.join(HERE, "sortquestions_log.txt")

ID_WIDTH = 5
TMP_PREFIX = "__tmp__"

RE_PRE_AUDIO = re.compile(r"^pre_audio_(\d{5})\.mp3$")
RE_AUDIO = re.compile(r"^question_(\d{5})\.mp3$")
RE_MANAGED_AUDIO = re.compile(r"^(pre_audio|question)_(\d{5})\.mp3$")


# ---------------------------
# Logging
# ---------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_log(lines: List[str]) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def log_header(seed: Optional[int], count: int) -> List[str]:
    return [
        "=== haveiever/questions.json shuffle + renumber + audio rename ===",
        f"timestamp_utc: {utc_now_iso()}",
        f"seed: {seed if seed is not None else 'None (random)'}",
        f"count: {count}",
        f"questions_path: {QUESTIONS_PATH}",
        f"media_audio_dir: {MEDIA_AUDIO_DIR}",
        "",
    ]


def abort_with_log(header: List[str], phase_lines: List[str], exit_code: int = 1) -> int:
    out = header + phase_lines + [""]
    append_log(out)
    for line in phase_lines:
        print(line)
    return exit_code


# ---------------------------
# JSON I/O
# ---------------------------

def load_questions(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} muss ein JSON-Array sein.")
    return data


def save_questions(path: str, questions: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)


# ---------------------------
# Preparation checks (Phase 1)
# ---------------------------

def join_media(filename: str) -> str:
    return os.path.join(MEDIA_AUDIO_DIR, filename)


def zfill_id(i: int) -> str:
    return str(i).zfill(ID_WIDTH)


def validate_json_audio_entries_against_files(questions: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    PHASE 1: beidseitiger Konsistenzcheck für den IST-Zustand
    - JSON -> Dateien: jede referenzierte Datei existiert
    - Dateien -> JSON: keine "managed audio"-Datei (pre_audio_XXXXX.mp3 / question_XXXXX.mp3) ist unreferenziert
    - Naming/ID-Konsistenz: Datei-ID == question.id
    """
    lines: List[str] = []
    lines.append("phase1_prepare_check:")

    if not os.path.isdir(MEDIA_AUDIO_DIR):
        lines.append(f"  ERROR: Audio-Ordner existiert nicht: {MEDIA_AUDIO_DIR}")
        return False, lines

    referenced: List[Tuple[str, str, str]] = []  # (qid, field, filename)
    referenced_set: Set[str] = set()
    duplicate_refs: Dict[str, List[str]] = {}

    # JSON -> Dateien, Naming + ID match
    for q in questions:
        qid = str(q.get("id", "") or "")
        if not re.fullmatch(r"\d{5}", qid):
            lines.append(f"  ERROR: Frage hat ungültige id (erwarte 5-stellig): {qid}")
            return False, lines

        pre_fn = str(q.get("pre_audio", "") or "")
        aud_fn = str(q.get("audio", "") or "")

        if pre_fn:
            m = RE_PRE_AUDIO.match(pre_fn)
            if not m:
                lines.append(f"  ERROR: pre_audio hat falsches Naming (erwarte pre_audio_<id>.mp3): {pre_fn} (q:{qid})")
                return False, lines
            if m.group(1) != qid:
                lines.append(f"  ERROR: pre_audio ID passt nicht zur Frage-ID: {pre_fn} (q:{qid})")
                return False, lines

            referenced.append((qid, "pre_audio", pre_fn))
            referenced_set.add(pre_fn)
            duplicate_refs.setdefault(pre_fn, []).append(f"q:{qid} pre_audio")

        if aud_fn:
            m = RE_AUDIO.match(aud_fn)
            if not m:
                lines.append(f"  ERROR: audio hat falsches Naming (erwarte question_<id>.mp3): {aud_fn} (q:{qid})")
                return False, lines
            if m.group(1) != qid:
                lines.append(f"  ERROR: audio ID passt nicht zur Frage-ID: {aud_fn} (q:{qid})")
                return False, lines

            referenced.append((qid, "audio", aud_fn))
            referenced_set.add(aud_fn)
            duplicate_refs.setdefault(aud_fn, []).append(f"q:{qid} audio")

    # Duplicate reference check (hart)
    dup_lines: List[str] = []
    for fn, refs in duplicate_refs.items():
        if len(refs) > 1:
            dup_lines.append(f"  ERROR: Datei wird mehrfach im JSON referenziert: {fn} -> {', '.join(refs)}")
    if dup_lines:
        lines.extend(dup_lines)
        return False, lines

    missing_lines: List[str] = []
    for qid, field, fn in referenced:
        if not os.path.exists(join_media(fn)):
            missing_lines.append(f"  ERROR: Datei fehlt (JSON->Datei): {fn} (q:{qid} {field})")
    if missing_lines:
        lines.extend(missing_lines)
        return False, lines

    # Dateien -> JSON (nur "managed audio" prüfen)
    managed_files: Set[str] = set()
    for fn in os.listdir(MEDIA_AUDIO_DIR):
        if RE_MANAGED_AUDIO.match(fn):
            managed_files.add(fn)

    extra_files = sorted(managed_files - referenced_set)
    if extra_files:
        lines.append("  ERROR: Es gibt Audio-Dateien im Ordner, die NICHT im JSON referenziert sind (Datei->JSON):")
        for fn in extra_files:
            lines.append(f"    - {fn}")
        return False, lines

    lines.append("  OK: JSON<->Audio-Dateien sind konsistent (IST-Zustand).")
    return True, lines


# ---------------------------
# Planning (after shuffle)
# ---------------------------

@dataclass
class RenameOp:
    question_old_id: str
    question_new_id: str
    field: str           # "pre_audio" | "audio"
    source_name: str
    target_name: str
    source_path: str
    target_path: str
    tmp_path: Optional[str] = None


def build_mapping_and_plan(
    questions_shuffled: List[Dict[str, Any]]
) -> Tuple[List[Tuple[str, str]], List[RenameOp], List[Dict[str, Any]]]:
    """
    Erstellt neues Mapping + Rename-Plan und updated_questions (im Speicher).
    Naming-Logik strikt:
      pre_audio => pre_audio_<new_id>.mp3
      audio     => question_<new_id>.mp3
    """
    id_mapping: List[Tuple[str, str]] = []
    rename_ops: List[RenameOp] = []
    updated_questions: List[Dict[str, Any]] = []

    for i, q in enumerate(questions_shuffled, start=1):
        old_id = str(q.get("id", "") or "")
        new_id = zfill_id(i)
        id_mapping.append((old_id, new_id))

        q_new = dict(q)
        q_new["id"] = new_id

        # pre_audio
        pre_src = str(q.get("pre_audio", "") or "")
        if pre_src:
            pre_tgt = f"pre_audio_{new_id}.mp3"
            rename_ops.append(
                RenameOp(
                    question_old_id=old_id,
                    question_new_id=new_id,
                    field="pre_audio",
                    source_name=pre_src,
                    target_name=pre_tgt,
                    source_path=join_media(pre_src),
                    target_path=join_media(pre_tgt),
                )
            )
            q_new["pre_audio"] = pre_tgt
        else:
            q_new["pre_audio"] = ""

        # audio
        aud_src = str(q.get("audio", "") or "")
        if aud_src:
            aud_tgt = f"question_{new_id}.mp3"
            rename_ops.append(
                RenameOp(
                    question_old_id=old_id,
                    question_new_id=new_id,
                    field="audio",
                    source_name=aud_src,
                    target_name=aud_tgt,
                    source_path=join_media(aud_src),
                    target_path=join_media(aud_tgt),
                )
            )
            q_new["audio"] = aud_tgt
        else:
            q_new["audio"] = ""

        updated_questions.append(q_new)

    return id_mapping, rename_ops, updated_questions


def validate_rename_plan(rename_ops: List[RenameOp]) -> Tuple[bool, List[str]]:
    """
    Plan-Validierung (nach Phase1 IST-Checks):
    - keine Target-Duplikate
    - kein Overwrite einer Datei, die NICHT Teil des Moves ist
      (Targets dürfen existieren, wenn sie gleichzeitig Source einer anderen Operation sind -> ok wegen TMP)
    """
    lines: List[str] = []
    lines.append("phase1_plan_validation:")

    # effektive ops
    effective_ops = [op for op in rename_ops if op.source_path != op.target_path]

    # target collision
    target_paths: Dict[str, RenameOp] = {}
    dup_targets: List[str] = []
    for op in effective_ops:
        if op.target_path in target_paths:
            other = target_paths[op.target_path]
            dup_targets.append(
                f"  ERROR: DUPLICATE_TARGET {op.target_name}\n"
                f"    1) {other.source_name} (q:{other.question_old_id}->{other.question_new_id}, {other.field})\n"
                f"    2) {op.source_name} (q:{op.question_old_id}->{op.question_new_id}, {op.field})"
            )
        else:
            target_paths[op.target_path] = op
    if dup_targets:
        lines.extend(dup_targets)
        return False, lines

    sources_being_moved: Set[str] = {op.source_path for op in effective_ops}

    # overwrite check (target exists but is not moved-away source)
    overwrites: List[str] = []
    for op in effective_ops:
        if os.path.exists(op.target_path) and op.target_path not in sources_being_moved:
            overwrites.append(
                f"  ERROR: TARGET_EXISTS_NOT_IN_PLAN {op.target_name} "
                f"(würde überschrieben werden) from {op.source_name}"
            )
    if overwrites:
        lines.extend(overwrites)
        return False, lines

    lines.append("  OK: Rename-Plan ist valide (keine Kollisionen/Overwrites außerhalb des Plans).")
    return True, lines


# ---------------------------
# Phase 2: Rename execution (TMP swap-safe)
# ---------------------------

def execute_rename(rename_ops: List[RenameOp]) -> List[str]:
    lines: List[str] = []
    lines.append("phase2_rename:")

    effective_ops = [op for op in rename_ops if op.source_path != op.target_path]
    if not effective_ops:
        lines.append("  (keine Umbenennungen notwendig)")
        return lines

    # SOURCE -> TMP
    moved_to_tmp: List[RenameOp] = []
    try:
        for op in effective_ops:
            tmp_name = f"{TMP_PREFIX}{os.path.basename(op.source_name)}.{uuid.uuid4().hex}"
            op.tmp_path = join_media(tmp_name)
            os.rename(op.source_path, op.tmp_path)
            moved_to_tmp.append(op)
            lines.append(
                f"  OK SOURCE->TMP q:{op.question_old_id}->{op.question_new_id} {op.field}: "
                f"{op.source_name} -> {os.path.basename(op.tmp_path)}"
            )
    except Exception as e:
        lines.append(f"  ERROR: SOURCE->TMP fehlgeschlagen: {repr(e)}")
        # Best-effort rollback: TMP -> SOURCE
        for op in reversed(moved_to_tmp):
            try:
                assert op.tmp_path is not None
                os.rename(op.tmp_path, op.source_path)
                lines.append(
                    f"  ROLLBACK TMP->SOURCE q:{op.question_old_id}->{op.question_new_id} {op.field}: "
                    f"{os.path.basename(op.tmp_path)} -> {op.source_name}"
                )
            except Exception as re_err:
                lines.append(
                    f"  ROLLBACK_ERROR q:{op.question_old_id}->{op.question_new_id} {op.field}: {repr(re_err)}"
                )
        raise

    # TMP -> TARGET
    moved_to_target: List[RenameOp] = []
    try:
        for op in effective_ops:
            assert op.tmp_path is not None
            os.rename(op.tmp_path, op.target_path)
            moved_to_target.append(op)
            lines.append(
                f"  OK TMP->TARGET q:{op.question_old_id}->{op.question_new_id} {op.field}: "
                f"{os.path.basename(op.tmp_path)} -> {op.target_name}"
            )
    except Exception as e:
        lines.append(f"  ERROR: TMP->TARGET fehlgeschlagen: {repr(e)}")
        # Best-effort rollback:
        # 1) bereits fertige TARGETs zurück auf TMP-namen (neu generiert)
        rollback_tmp_paths: List[Tuple[str, str]] = []  # (target_path, new_tmp_path)
        for op in reversed(moved_to_target):
            try:
                new_tmp = join_media(f"{TMP_PREFIX}rollback.{uuid.uuid4().hex}")
                os.rename(op.target_path, new_tmp)
                rollback_tmp_paths.append((op.source_path, new_tmp))
                lines.append(
                    f"  ROLLBACK TARGET->TMP q:{op.question_old_id}->{op.question_new_id} {op.field}: "
                    f"{op.target_name} -> {os.path.basename(new_tmp)}"
                )
            except Exception as re_err:
                lines.append(
                    f"  ROLLBACK_ERROR (target->tmp) q:{op.question_old_id}->{op.question_new_id} {op.field}: {repr(re_err)}"
                )
        # 2) alle TMPs (die noch existieren) zurück auf SOURCE, plus die rollback_tmps
        for op in reversed(effective_ops):
            # wenn tmp_path noch existiert (nicht zu target geworden), zurück
            try:
                if op.tmp_path and os.path.exists(op.tmp_path):
                    os.rename(op.tmp_path, op.source_path)
                    lines.append(
                        f"  ROLLBACK TMP->SOURCE q:{op.question_old_id}->{op.question_new_id} {op.field}: "
                        f"{os.path.basename(op.tmp_path)} -> {op.source_name}"
                    )
            except Exception as re_err:
                lines.append(
                    f"  ROLLBACK_ERROR (tmp->source) q:{op.question_old_id}->{op.question_new_id} {op.field}: {repr(re_err)}"
                )
        for source_path, tmp_path in rollback_tmp_paths:
            try:
                os.rename(tmp_path, source_path)
                lines.append(
                    f"  ROLLBACK TMP->SOURCE (from target) {os.path.basename(tmp_path)} -> {os.path.basename(source_path)}"
                )
            except Exception as re_err:
                lines.append(f"  ROLLBACK_ERROR (tmp->source from target): {repr(re_err)}")
        raise

    return lines


# ---------------------------
# Phase 3: Post-check
# ---------------------------

def validate_final_state(updated_questions: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    lines: List[str] = []
    lines.append("phase3_postcheck:")

    if not os.path.isdir(MEDIA_AUDIO_DIR):
        lines.append(f"  ERROR: Audio-Ordner existiert nicht: {MEDIA_AUDIO_DIR}")
        return False, lines

    # TMP leftovers
    leftovers = [fn for fn in os.listdir(MEDIA_AUDIO_DIR) if fn.startswith(TMP_PREFIX)]
    if leftovers:
        lines.append("  ERROR: LEFTOVER_TMP_FILES:")
        for fn in leftovers:
            lines.append(f"    - {fn}")
        return False, lines

    # JSON->File + strict naming
    referenced_set: Set[str] = set()
    for q in updated_questions:
        qid = str(q.get("id", "") or "")
        if not re.fullmatch(r"\d{5}", qid):
            lines.append(f"  ERROR: Ungültige Frage-ID nach Update: {qid}")
            return False, lines

        pre_fn = str(q.get("pre_audio", "") or "")
        aud_fn = str(q.get("audio", "") or "")

        if pre_fn:
            expected = f"pre_audio_{qid}.mp3"
            if pre_fn != expected:
                lines.append(f"  ERROR: pre_audio passt nicht exakt zum Schema: {pre_fn} (erwarte {expected})")
                return False, lines
            if not os.path.exists(join_media(pre_fn)):
                lines.append(f"  ERROR: Datei fehlt nach Rename: {pre_fn} (q:{qid} pre_audio)")
                return False, lines
            referenced_set.add(pre_fn)

        if aud_fn:
            expected = f"question_{qid}.mp3"
            if aud_fn != expected:
                lines.append(f"  ERROR: audio passt nicht exakt zum Schema: {aud_fn} (erwarte {expected})")
                return False, lines
            if not os.path.exists(join_media(aud_fn)):
                lines.append(f"  ERROR: Datei fehlt nach Rename: {aud_fn} (q:{qid} audio)")
                return False, lines
            referenced_set.add(aud_fn)

    # File->JSON (managed audio)
    managed_files = {fn for fn in os.listdir(MEDIA_AUDIO_DIR) if RE_MANAGED_AUDIO.match(fn)}
    extra_files = sorted(managed_files - referenced_set)
    if extra_files:
        lines.append("  ERROR: Es gibt Audio-Dateien, die nach dem Rename NICHT im JSON referenziert sind:")
        for fn in extra_files:
            lines.append(f"    - {fn}")
        return False, lines

    lines.append("  POSTCHECK_OK")
    return True, lines


# ---------------------------
# Main
# ---------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None, help="Optionaler Random-Seed (für reproduzierbare Reihenfolge).")
    args = parser.parse_args()

    header = log_header(args.seed, 0)

    if not os.path.exists(QUESTIONS_PATH):
        return abort_with_log(header, [f"phase0_error:", f"  ERROR: Nicht gefunden: {QUESTIONS_PATH}"])

    questions = load_questions(QUESTIONS_PATH)
    header = log_header(args.seed, len(questions))

    # -------------------------
    # PHASE 1: IST-Konsistenzcheck (vor Shuffle/Rename)
    # -------------------------
    ok, phase1_lines = validate_json_audio_entries_against_files(questions)
    if not ok:
        return abort_with_log(header, phase1_lines)

    # Shuffle + Plan
    rng = random.Random(args.seed)
    questions_shuffled = list(questions)
    rng.shuffle(questions_shuffled)

    id_mapping, rename_ops, updated_questions = build_mapping_and_plan(questions_shuffled)

    # Plan-Validation (keine Kollisionen / keine Overwrites außerhalb des Plans)
    ok_plan, plan_lines = validate_rename_plan(rename_ops)
    if not ok_plan:
        # Zusätzlich Mapping/Plan in Log schreiben (damit du siehst, was geplant war)
        extra: List[str] = []
        extra.append("phase1_plan_mapping:")
        for old_id, new_id in id_mapping:
            extra.append(f"  {old_id} -> {new_id}")
        extra.append("phase1_plan_renames:")
        for op in rename_ops:
            extra.append(f"  {op.field} q:{op.question_old_id}->{op.question_new_id}: {op.source_name} -> {op.target_name}")
        return abort_with_log(header, plan_lines + extra)

    # Protokoll: Mapping + Plan (ok)
    prelog: List[str] = []
    prelog.extend(phase1_lines)
    prelog.append("")
    prelog.append("phase1_plan_mapping:")
    for old_id, new_id in id_mapping:
        prelog.append(f"  {old_id} -> {new_id}")
    prelog.append("phase1_plan_renames:")
    for op in rename_ops:
        prelog.append(f"  {op.field} q:{op.question_old_id}->{op.question_new_id}: {op.source_name} -> {op.target_name}")
    prelog.append("")
    prelog.extend(plan_lines)
    prelog.append("")
    append_log(header + prelog + [""])

    # -------------------------
    # PHASE 2: Rename + JSON schreiben
    # -------------------------
    try:
        phase2_lines = execute_rename(rename_ops)
    except Exception as e:
        # rename error already best-effort rolled back; log + abort
        err_lines = ["phase2_abort:", f"  ERROR: Rename fehlgeschlagen: {repr(e)}", "  (siehe Log für Details)"]
        append_log(header + phase2_lines + err_lines + [""])
        for line in err_lines:
            print(line)
        return 1

    # JSON speichern (erst nach erfolgreichem Rename)
    save_questions(QUESTIONS_PATH, updated_questions)

    # -------------------------
    # PHASE 3: Postcheck
    # -------------------------
    ok_post, phase3_lines = validate_final_state(updated_questions)

    final_log: List[str] = []
    final_log.extend(phase2_lines)
    final_log.append("phase2_json_update:")
    final_log.append("  OK: questions.json geschrieben")
    final_log.append("")
    final_log.extend(phase3_lines)
    final_log.append("")

    append_log(final_log)

    if not ok_post:
        for line in phase3_lines:
            print(line)
        print(f"FEHLER: Postcheck nicht ok. Log: {LOG_PATH}")
        return 1

    print(f"OK: {len(updated_questions)} Fragen gemischt, IDs/Audios umbenannt, alles geprüft.")
    print(f"- updated: {QUESTIONS_PATH}")
    print(f"- log:     {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
