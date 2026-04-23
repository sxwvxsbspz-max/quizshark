import os
import random
import json
import uuid
import threading
from datetime import datetime, timezone, timedelta

import requests

from engine.questions_json import load_json_questions, save_json_questions, now_iso_utc, lastplayed_ts

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_MODULE_DIR, ".."))

_OPENAI_KEY_PATH = os.path.join(_PROJECT_ROOT, "openaiapi.json")
_11LABS_KEY_PATH = os.path.join(_PROJECT_ROOT, "11labsapi.json")
_PS_QUESTIONS    = os.path.join(_PROJECT_ROOT, "punktesammler", "questions.json")
_OWN_QUESTIONS   = os.path.join(_MODULE_DIR, "questions.json")
_AUDIO_DIR       = os.path.join(_MODULE_DIR, "media", "audio")
_PS_AUDIO_URL    = "/punktesammler/media/audio"

# ---------------------------------------------------------------------------
# ELEVENLABS SETTINGS
# ---------------------------------------------------------------------------

_VOICE_ID      = "re2r5d74PqDzicySNW0I"
_MODEL_ID      = "eleven_v3"
_OUTPUT_FORMAT = "mp3_44100_192"
_TTS_PREFIX    = "[confident] [energetic] "

# ---------------------------------------------------------------------------
# HELPERS: keys
# ---------------------------------------------------------------------------

def _openai_key() -> str:
    k = os.environ.get("OPENAI_API_KEY", "").strip()
    if k:
        return k
    with open(_OPENAI_KEY_PATH, "r", encoding="utf-8") as f:
        return (json.load(f).get("OPENAI_API_KEY") or "").strip()


def _11labs_key() -> str:
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if k:
        return k
    with open(_11LABS_KEY_PATH, "r", encoding="utf-8") as f:
        return (json.load(f).get("api_key") or "").strip()


# ---------------------------------------------------------------------------
# CUSTOM EXCEPTIONS
# ---------------------------------------------------------------------------

class ContentPolicyError(Exception):
    pass

class NonsenseError(Exception):
    pass


# ---------------------------------------------------------------------------
# REFUSAL DETECTION
# ---------------------------------------------------------------------------

_REFUSAL_KW = [
    "kann ich nicht", "kann keine", "nicht erstellen", "nicht möglich",
    "leider nicht", "inappropriate", "nicht beantworten", "lehne ab",
    "verweigere", "problematisch", "not able to", "cannot", "unable to",
    "i'm sorry", "i cannot", "i'm unable",
]


def _looks_like_refusal(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _REFUSAL_KW)


# ---------------------------------------------------------------------------
# GPT CALL
# ---------------------------------------------------------------------------

def _call_gpt(category: str) -> dict:
    from openai import OpenAI, BadRequestError

    prompt = (
        f'Erstelle eine Multiple-Choice-Quiz-Frage auf Deutsch zum Thema "{category}".\n\n'
        'Anforderungen:\n'
        '- Frage und Antworten auf Deutsch\n'
        '- Eher Anspruchsvoll, aber nicht sehr schwer (Nicht super leicht!)\n'
        '- Richtige Antwort zu 100%% korrekt und eindeutig\n'
        '- 3 falsche Antworten: plausibel, aber eindeutig falsch\n'
        '- Keine offensichtlich einfachen oder kindergeeigneten Fragen\n\n'
        'Antworte NUR mit einem JSON-Objekt ohne Markdown:\n'
        '{"question": "...", "correct": "...", "wrong": ["...", "...", "..."]}'
    )

    client = OpenAI(api_key=_openai_key())

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
    except BadRequestError as e:
        msg = str(e).lower()
        if "content_policy" in msg or "rejected" in msg or "safety" in msg:
            raise ContentPolicyError(str(e))
        raise

    raw = resp.choices[0].message.content.strip()

    if "```" in raw:
        s = raw.find("{")
        e2 = raw.rfind("}") + 1
        if s >= 0 and e2 > s:
            raw = raw[s:e2]

    if "{" not in raw and _looks_like_refusal(raw):
        raise ContentPolicyError(f"GPT refused: {raw[:120]}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        if _looks_like_refusal(raw):
            raise ContentPolicyError(f"GPT refused (no JSON): {raw[:120]}")
        raise NonsenseError(f"No valid JSON: {raw[:120]}")

    if not isinstance(parsed, dict):
        raise NonsenseError("Response is not a JSON object")

    return parsed


def _validate(q: dict) -> dict:
    """Raises NonsenseError if structure is wrong. Returns cleaned dict."""
    text  = (q.get("question") or "").strip()
    cor   = (q.get("correct")  or "").strip()
    wrong = q.get("wrong")

    if not text:
        raise NonsenseError("Empty question text")
    if not cor:
        raise NonsenseError("Empty correct answer")
    if not isinstance(wrong, list) or len(wrong) != 3:
        raise NonsenseError(f"Expected 3 wrong answers, got: {wrong!r}")

    wrong_s = [str(w).strip() for w in wrong]
    if any(not w for w in wrong_s):
        raise NonsenseError("Empty wrong answer(s)")
    if cor.lower() in [w.lower() for w in wrong_s]:
        raise NonsenseError("Correct answer duplicated in wrong answers")

    return {"question": text, "correct": cor, "wrong": wrong_s}


# ---------------------------------------------------------------------------
# ELEVENLABS TTS
# ---------------------------------------------------------------------------

def _generate_tts(text: str, audio_id: str) -> str:
    """Calls ElevenLabs, saves MP3 to AUDIO_DIR. Returns filename."""
    os.makedirs(_AUDIO_DIR, exist_ok=True)

    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{_VOICE_ID}"
        f"?output_format={_OUTPUT_FORMAT}"
    )
    headers = {
        "xi-api-key": _11labs_key(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": f"{_TTS_PREFIX}{text.rstrip('?')}.",
        "model_id": _MODEL_ID,
        "voice_settings": {"stability": 0.5},
    }

    r = requests.post(url, json=body, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:200]}")

    filename = f"question-{audio_id}.mp3"
    with open(os.path.join(_AUDIO_DIR, filename), "wb") as f:
        f.write(r.content)

    return filename


# ---------------------------------------------------------------------------
# QUESTION BANK HELPERS
# ---------------------------------------------------------------------------

def _pick_questions_for_players(players: dict) -> dict:
    """Assigns 3 PS questions (distinct categories) to each player."""
    try:
        qs = load_json_questions(_PS_QUESTIONS)
    except Exception:
        return {}

    valid = [
        q for q in qs
        if q.get("question") and q.get("correct") and
           isinstance(q.get("wrong"), list) and len(q["wrong"]) == 3 and
           q.get("audio") and q.get("category")
    ]
    if not valid:
        return {}

    valid.sort(key=lambda q: (lastplayed_ts(q), int(q.get("id", 0) or 0)))

    used_ids: set = set()
    result: dict = {}

    for pid in players:
        options = []
        seen_cats: set = set()

        # First pass: prefer questions not yet assigned to other players
        for q in valid:
            cat = q["category"].strip()
            if cat in seen_cats or q["id"] in used_ids:
                continue
            options.append(q)
            seen_cats.add(cat)
            used_ids.add(q["id"])
            if len(options) >= 3:
                break

        # Second pass: allow reuse if question bank is small
        if len(options) < 3:
            for q in valid:
                if q in options:
                    continue
                cat = q["category"].strip()
                if cat in seen_cats:
                    continue
                options.append(q)
                seen_cats.add(cat)
                if len(options) >= 3:
                    break

        if options:
            result[pid] = options

    return result


def _update_ps_lastplayed(question_id: str):
    try:
        qs = load_json_questions(_PS_QUESTIONS)
        for q in qs:
            if q.get("id") == question_id:
                q["lastplayed"] = now_iso_utc()
                break
        save_json_questions(_PS_QUESTIONS, qs)
    except Exception as e:
        print(f"[YourCategory] lastplayed update failed for {question_id}: {e}")


def _load_inspiration() -> list:
    """All categories that have appeared in yourcategory/questions.json."""
    try:
        if not os.path.exists(_OWN_QUESTIONS):
            return []
        qs = load_json_questions(_OWN_QUESTIONS)
        cats = list({(q.get("category") or "").strip() for q in qs if q.get("category")})
        return [c for c in cats if c]
    except Exception:
        return []


def _save_question(q_data: dict):
    try:
        qs = load_json_questions(_OWN_QUESTIONS) if os.path.exists(_OWN_QUESTIONS) else []
    except Exception:
        qs = []
    qs.append(q_data)
    save_json_questions(_OWN_QUESTIONS, qs)


# ---------------------------------------------------------------------------
# MAIN LOGIC
# ---------------------------------------------------------------------------

class YourCategoryLogic:

    # --- Configurable ---
    MAX_QUESTIONS             = 10
    INTRO_MAX_WAIT_SECONDS    = 60
    CATEGORY_INPUT_SECONDS    = 60
    GPT_TIMEOUT_SECONDS       = 20
    TTS_TIMEOUT_SECONDS       = 30
    ERROR_WAIT_SECONDS        = 4
    ANNOUNCEMENT_WAIT_SECONDS = 7
    INTRO_DELAY_SECONDS       = 3
    ANSWER_DURATION_SECONDS   = 15
    REVEAL_DELAY_SECONDS      = 2
    UNVEIL_DELAY_SECONDS      = 2
    RESOLUTION_DELAY_SECONDS  = 2
    SCORING_SHOW_SECONDS      = 2
    SCORING_HOLD_SECONDS      = 2

    def __init__(self, socketio, players, on_game_finished=None):
        self.socketio         = socketio
        self.players          = players
        self.on_game_finished = on_game_finished

        self.state      = "INTRO"
        self._finished  = False
        self._finalized = False

        # Phase 1
        self.player_question_options   = _pick_questions_for_players(players)  # pid -> [q, q, q]
        self.player_selected_questions = {}   # pid -> chosen PS q_dict (wenn Vorschlag gewählt)
        self.player_categories         = {}   # pid -> category string (für alle Spieler, egal ob PS oder KI)
        self.inspiration_categories    = _load_inspiration()
        self._input_ends_at            = None

        # Phase 2
        self.manual_players      = []   # [(pid, name, category)] – manuell eingetippt
        self.ps_players          = []   # [(pid, name, ps_q)]     – PS-Vorschlag geklickt
        self.generated_questions = []
        self._gen_progress       = 0
        self._gen_total          = 0

        # Phase 3
        self.current_question_index = 0
        self.player_answers         = {}
        self._current_q_payload     = None
        self._current_correct_index = None
        self._answer_started_at     = None
        self._answer_ends_at        = None
        self._announcement_event    = None

        self.socketio.start_background_task(self._intro_wait_task)

    # -----------------------------------------------------------------------
    # ISO helper
    # -----------------------------------------------------------------------

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # -----------------------------------------------------------------------
    # Rankings
    # -----------------------------------------------------------------------

    def _ranked(self) -> list:
        items = [
            {"player_id": pid,
             "name": p.get("name", ""),
             "score": int(p.get("score", 0) or 0)}
            for pid, p in self.players.items()
        ]
        items.sort(key=lambda x: (-x["score"], (x["name"] or "").lower(), x["player_id"]))
        return items

    # -----------------------------------------------------------------------
    # INTRO
    # -----------------------------------------------------------------------

    def _intro_wait_task(self):
        self.socketio.sleep(float(self.INTRO_MAX_WAIT_SECONDS))
        self._trigger_category_input()

    def _trigger_category_input(self):
        if self.state != "INTRO" or self._finished:
            return
        self._start_category_input()

    # -----------------------------------------------------------------------
    # PHASE 1 – CATEGORY INPUT
    # -----------------------------------------------------------------------

    def _player_options_payload(self) -> dict:
        """Per-player option list for controller: {pid: [{id, category}, ...]}"""
        return {
            pid: [{"id": q["id"], "category": q["category"]} for q in opts]
            for pid, opts in self.player_question_options.items()
        }

    def _start_category_input(self):
        self.state = "CATEGORY_INPUT"
        started = datetime.now(timezone.utc)
        ends    = started + timedelta(seconds=self.CATEGORY_INPUT_SECONDS)
        self._input_ends_at = ends

        payload = {
            "state":                  "CATEGORY_INPUT",
            "duration":               self.CATEGORY_INPUT_SECONDS,
            "started_at":             self._iso(started),
            "ends_at":                self._iso(ends),
            "player_options":         self._player_options_payload(),
            "inspiration_categories": self.inspiration_categories,
            "players_ranked":         self._ranked(),
            "submitted":              [],
        }
        self.socketio.emit("yc_category_input", payload, room="tv_room")
        self.socketio.emit("yc_category_input", payload, room="controller_room")
        self.socketio.start_background_task(self._input_timer_task)

    def _input_timer_task(self):
        self.socketio.sleep(float(self.CATEGORY_INPUT_SECONDS))
        self._finalize_categories()

    def _handle_submit_category(self, player_id: str, question_id: str, category: str):
        if self.state != "CATEGORY_INPUT":
            return
        # Bereits abgestimmt (egal ob PS-Frage oder eigene Kategorie)
        if player_id in self.player_categories:
            return

        if question_id:
            # Spieler hat einen der 3 Vorschläge geklickt → PS-Frage direkt verwenden
            options = self.player_question_options.get(player_id, [])
            chosen = next((q for q in options if q.get("id") == question_id), None)
            if not chosen:
                return
            self.player_selected_questions[player_id] = chosen
            self.player_categories[player_id] = chosen.get("category", "")
        elif category.strip():
            # Spieler hat selbst etwas eingetippt → KI generiert
            self.player_categories[player_id] = category.strip()
        else:
            return

        self.socketio.emit("yc_player_submitted", {
            "player_id":       player_id,
            "submitted_count": len(self.player_categories),
            "total_players":   len(self.players),
        }, room="tv_room")

        if len(self.player_categories) >= len(self.players):
            self._finalize_categories()

    def _finalize_categories(self):
        if self._finalized or self._finished:
            return
        self._finalized = True

        manual, ps = [], []
        for pid, pdata in self.players.items():
            name = pdata.get("name", pid)
            if pid not in self.player_categories:
                continue  # Keine Abgabe → ignorieren
            if pid in self.player_selected_questions:
                ps.append((pid, name, self.player_selected_questions[pid]))
            else:
                manual.append((pid, name, self.player_categories[pid]))

        random.shuffle(manual)
        random.shuffle(ps)

        self.manual_players = manual
        self.ps_players     = ps
        self._gen_total     = min(len(manual) + len(ps), self.MAX_QUESTIONS)

        self._start_generating()

    # -----------------------------------------------------------------------
    # PHASE 2 – GENERATING
    # -----------------------------------------------------------------------

    def _start_generating(self):
        self.state         = "GENERATING"
        self._gen_progress = 0

        gen_payload = {
            "state":          "GENERATING",
            "progress":       0,
            "total":          self._gen_total,
            "players_ranked": self._ranked(),
        }
        self.socketio.emit("yc_generating", gen_payload, room="tv_room")
        self.socketio.emit("yc_generating", gen_payload, room="controller_room")
        self.socketio.start_background_task(self._generation_task)

    def _emit_gen_progress(self, player_name: str, category: str):
        self.socketio.emit("yc_generating", {
            "state":            "GENERATING",
            "progress":         len(self.generated_questions),
            "total":            self._gen_total,
            "current_category": category,
            "current_player":   player_name,
        }, room="tv_room")

    def _generation_task(self):
        skipped = []   # (pid, name, category, error_type) – manuelle Spieler bei denen KI scheiterte

        # --- Phase 1: Manuelle Spieler → KI ---
        for pid, name, category in self.manual_players:
            if self._finished:
                return
            if len(self.generated_questions) >= self._gen_total:
                break

            self._emit_gen_progress(name, category)

            error_type = None
            try:
                raw       = self._gpt_threaded(category)
                validated = _validate(raw)
                q_id      = uuid.uuid4().hex[:8]
                audio     = self._tts_threaded(validated["question"], q_id)

                q_data = {
                    "id":                q_id,
                    "category":          category,
                    "question":          validated["question"],
                    "correct":           validated["correct"],
                    "wrong":             validated["wrong"],
                    "audio":             audio,
                    "image":             "",
                    "lastplayed":        now_iso_utc(),
                    "submitted_by":      pid,
                    "submitted_by_name": name,
                }
                self.generated_questions.append(q_data)
                _save_question(q_data)
                self._gen_progress = len(self.generated_questions)

            except ContentPolicyError:
                error_type = "content_policy"
            except NonsenseError:
                error_type = "nonsense"
            except Exception:
                error_type = "technical"

            if error_type:
                self.socketio.emit("yc_error", {
                    "sound_type":  error_type,
                    "player_name": name,
                    "category":    category,
                }, room="tv_room")
                skipped.append((pid, name, category, error_type))
                self.socketio.sleep(float(self.ERROR_WAIT_SECONDS))

        # --- Phase 2: PS-Spieler → direkt auffüllen ---
        for pid, name, ps_q in self.ps_players:
            if self._finished:
                return
            if len(self.generated_questions) >= self._gen_total:
                break

            self._emit_gen_progress(name, ps_q.get("category", ""))

            q_data = {
                "id":                ps_q["id"],
                "category":          ps_q.get("category", ""),
                "question":          ps_q["question"],
                "correct":           ps_q["correct"],
                "wrong":             list(ps_q["wrong"]),
                "audio":             f"{_PS_AUDIO_URL}/{ps_q['audio']}",
                "image":             ps_q.get("image", ""),
                "submitted_by":      pid,
                "submitted_by_name": name,
                "_ps_source":        True,
            }
            self.generated_questions.append(q_data)
            self._gen_progress = len(self.generated_questions)

        # --- Phase 3: Übersprungene manuelle Spieler → PS-Fallback ---
        for pid, name, category, error_type in skipped:
            if self._finished:
                return
            if len(self.generated_questions) >= self._gen_total:
                break

            self._emit_gen_progress(name, category)
            self.socketio.emit("yc_error", {
                "sound_type":  error_type,
                "player_name": name,
                "category":    category,
            }, room="tv_room")

            fallback = self._pick_ps_fallback(pid)
            if fallback:
                fb_data = {
                    "id":                fallback["id"],
                    "category":          fallback.get("category", ""),
                    "question":          fallback["question"],
                    "correct":           fallback["correct"],
                    "wrong":             list(fallback["wrong"]),
                    "audio":             f"{_PS_AUDIO_URL}/{fallback['audio']}",
                    "image":             fallback.get("image", ""),
                    "submitted_by":      pid,
                    "submitted_by_name": name,
                    "_ps_source":        True,
                }
                self.generated_questions.append(fb_data)
                self._gen_progress = len(self.generated_questions)

            self.socketio.sleep(float(self.ERROR_WAIT_SECONDS))

        # Alles durchmischen damit Reihenfolge nicht vorhersehbar ist
        random.shuffle(self.generated_questions)

        if not self._finished:
            self._start_questions()

    # --- threaded helpers ---

    def _gpt_threaded(self, category: str) -> dict:
        result, error = [None], [None]
        def _run():
            try:
                result[0] = _call_gpt(category)
            except Exception as e:
                error[0] = e
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=self.GPT_TIMEOUT_SECONDS)
        if t.is_alive():
            raise TimeoutError(f"GPT timeout ({self.GPT_TIMEOUT_SECONDS}s)")
        if error[0] is not None:
            raise error[0]
        return result[0]

    def _tts_threaded(self, text: str, audio_id: str) -> str:
        result, error = [None], [None]
        def _run():
            try:
                result[0] = _generate_tts(text, audio_id)
            except Exception as e:
                error[0] = e
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=self.TTS_TIMEOUT_SECONDS)
        if t.is_alive():
            raise TimeoutError(f"TTS timeout ({self.TTS_TIMEOUT_SECONDS}s)")
        if error[0] is not None:
            raise error[0]
        return result[0]

    def _pick_ps_fallback(self, pid: str) -> dict | None:
        """Gibt eine zufällige PS-Frage zurück, die noch nicht in generated_questions ist."""
        used_ids = {q["id"] for q in self.generated_questions}

        # Erst aus den vorher zugewiesenen Optionen des Spielers
        own_opts = [q for q in self.player_question_options.get(pid, []) if q["id"] not in used_ids]
        if own_opts:
            return random.choice(own_opts)

        # Sonst aus dem gesamten PS-Pool
        try:
            qs = load_json_questions(_PS_QUESTIONS)
        except Exception:
            return None

        valid = [
            q for q in qs
            if q.get("question") and q.get("correct") and
               isinstance(q.get("wrong"), list) and len(q["wrong"]) == 3 and
               q.get("audio") and q.get("category") and
               q["id"] not in used_ids
        ]
        return random.choice(valid) if valid else None

    # -----------------------------------------------------------------------
    # PHASE 3 – QUESTIONS
    # -----------------------------------------------------------------------

    def _start_questions(self):
        if not self.generated_questions:
            self._finish()
            return
        self.current_question_index = 0
        self._run_next_question()

    def _run_next_question(self):
        if self._finished:
            return
        if self.current_question_index >= len(self.generated_questions):
            self._finish()
            return
        q = self.generated_questions[self.current_question_index]
        self.socketio.start_background_task(self._question_task, q)

    def _question_task(self, q: dict):
        if self._finished:
            return

        # --- ANNOUNCEMENT ---
        self.state          = "ANNOUNCEMENT"
        self.player_answers = {}

        ann_num = random.randint(1, 10)
        ann_payload_tv = {
            "state":              "ANNOUNCEMENT",
            "player_id":          q["submitted_by"],
            "player_name":        q["submitted_by_name"],
            "category":           q["category"],
            "question_number":    self.current_question_index + 1,
            "total_questions":    len(self.generated_questions),
            "announcement_audio": f"categoryannouncement{ann_num}.mp3",
            "players_ranked":     self._ranked(),
        }
        ann_payload_ctrl = {k: v for k, v in ann_payload_tv.items() if k != "announcement_audio"}

        self._announcement_event = threading.Event()
        self.socketio.emit("yc_announcement", ann_payload_tv,   room="tv_room")
        self.socketio.emit("yc_announcement", ann_payload_ctrl, room="controller_room")

        self._announcement_event.wait(timeout=float(self.ANNOUNCEMENT_WAIT_SECONDS))
        self._announcement_event = None
        if self._finished:
            return

        # --- BUILD QUESTION ---
        options       = list(q["wrong"]) + [q["correct"]]
        random.shuffle(options)
        correct_index = options.index(q["correct"])

        # --- SHOW QUESTION ---
        self.state = "QUESTION_INTRO"
        unveil_at  = datetime.now(timezone.utc) + timedelta(seconds=self.INTRO_DELAY_SECONDS)
        q_payload  = {
            "text":              q["question"],
            "options":           options,
            "correct_index":     correct_index,
            "audio":             q["audio"],
            "image":             q.get("image", ""),
            "players_ranked":    self._ranked(),
            "answers_unveil_at": self._iso(unveil_at),
            "round":             self.current_question_index + 1,
        }
        self._current_q_payload     = q_payload
        self._current_correct_index = correct_index

        self.socketio.emit("show_question", q_payload, room="tv_room")
        self.socketio.emit("show_question", q_payload, room="controller_room")

        self.socketio.sleep(float(self.INTRO_DELAY_SECONDS))
        if self._finished:
            return

        # --- OPEN ANSWERS ---
        self.state = "OPEN_ANSWERS"
        now  = datetime.now(timezone.utc)
        ends = now + timedelta(seconds=self.ANSWER_DURATION_SECONDS)
        self._answer_started_at = now
        self._answer_ends_at    = ends

        open_payload = {
            "duration":       self.ANSWER_DURATION_SECONDS,
            "total_duration": self.ANSWER_DURATION_SECONDS,
            "started_at":     self._iso(now),
            "ends_at":        self._iso(ends),
        }
        self.socketio.emit("open_answers", open_payload, room="tv_room")
        self.socketio.emit("open_answers", open_payload, room="controller_room")

        _poll = 0.25
        _left = float(self.ANSWER_DURATION_SECONDS)
        while _left > 0 and not self._finished:
            self.socketio.sleep(min(_poll, _left))
            _left -= _poll
            if len(self.player_answers) >= len(self.players):
                break
        if self._finished:
            return

        # --- CLOSE ANSWERS ---
        self.state = "CLOSE_ANSWERS"
        self.socketio.emit("close_answers", {}, room="tv_room")
        self.socketio.emit("close_answers", {}, room="controller_room")

        self.socketio.sleep(float(self.REVEAL_DELAY_SECONDS))
        if self._finished:
            return

        # --- REVEAL PLAYER ANSWERS ---
        self.state = "REVEAL"
        self.socketio.emit("reveal_player_answers", {
            "player_answers": dict(self.player_answers),
            "correct_index":  correct_index,
        }, room="tv_room")
        self.socketio.emit("reveal_player_answers", {
            "player_answers": dict(self.player_answers),
            "correct_index":  correct_index,
        }, room="controller_room")

        self.socketio.sleep(float(self.UNVEIL_DELAY_SECONDS))
        if self._finished:
            return

        # --- UNVEIL CORRECT ---
        self.state = "UNVEIL"
        self.socketio.emit("unveil_correct", {"correct_index": correct_index}, room="tv_room")
        self.socketio.emit("unveil_correct", {"correct_index": correct_index}, room="controller_room")

        self.socketio.sleep(float(self.RESOLUTION_DELAY_SECONDS))
        if self._finished:
            return

        # --- SHOW RESOLUTION ---
        self.state = "RESOLUTION"
        self.socketio.emit("show_resolution", {
            "correct_index":  correct_index,
            "player_answers": dict(self.player_answers),
        }, room="tv_room")
        self.socketio.emit("show_resolution", {
            "correct_index":  correct_index,
            "player_answers": dict(self.player_answers),
        }, room="controller_room")

        self.socketio.sleep(float(self.SCORING_SHOW_SECONDS))
        if self._finished:
            return

        # --- SCORING ---
        self.state = "SCORING"

        ranked_before = self._ranked()

        gained = {}
        for pid in self.players:
            ans = self.player_answers.get(pid)
            if ans is not None and int(ans) == correct_index:
                self.players[pid]["score"] = int(self.players[pid].get("score", 0) or 0) + 100
                gained[pid] = 100
            else:
                gained[pid] = 0

        ranked_after = self._ranked()
        any_points = any(v != 0 for v in gained.values())

        if not any_points:
            self.socketio.sleep(float(self.SCORING_HOLD_SECONDS))
        else:
            self.socketio.emit("show_scoring", {
                "gained":         gained,
                "correct_index":  correct_index,
                "player_answers": dict(self.player_answers),
                "players_ranked": ranked_before,
                "show_pop":       True,
                "phase":          "pop",
            }, room="tv_room")
            self.socketio.emit("show_scoring", {
                "gained":         gained,
                "correct_index":  correct_index,
                "player_answers": dict(self.player_answers),
                "players_ranked": ranked_before,
                "show_pop":       True,
                "phase":          "pop",
            }, room="controller_room")

            self.socketio.sleep(float(self.SCORING_SHOW_SECONDS))
            if self._finished:
                return

            self.socketio.emit("apply_scoring_update", {"players_ranked": ranked_after}, room="tv_room")
            self.socketio.emit("apply_scoring_update", {"players_ranked": ranked_after}, room="controller_room")

            self.socketio.sleep(float(self.SCORING_HOLD_SECONDS))
        if self._finished:
            return

        # lastplayed in Punktesammler aktualisieren wenn die Frage von dort kam
        if q.get("_ps_source"):
            _update_ps_lastplayed(q["id"])

        self.current_question_index += 1
        self._run_next_question()

    # -----------------------------------------------------------------------
    # EVENT HANDLER (called from app.py)
    # -----------------------------------------------------------------------

    def handle_event(self, player_id: str, action: str, payload: dict):
        payload = payload or {}
        if self._finished:
            return

        if action == "video_finished":
            if self.state == "INTRO":
                self._trigger_category_input()

        elif action == "announcement_finished":
            if self._announcement_event:
                self._announcement_event.set()

        elif action == "submit_category":
            self._handle_submit_category(
                player_id,
                payload.get("question_id", ""),
                payload.get("category", ""),
            )

        elif action == "submit_answer":
            self._handle_answer(player_id, payload.get("index"))

    def _handle_answer(self, player_id: str, index):
        if self.state != "OPEN_ANSWERS":
            return
        if player_id in self.player_answers:
            return
        if index is None:
            return
        self.player_answers[player_id] = int(index)
        self.socketio.emit("player_logged_in", {"player_id": player_id}, room="tv_room")

    # -----------------------------------------------------------------------
    # SYNC (Reconnect)
    # -----------------------------------------------------------------------

    def _sync_payload_input(self) -> dict:
        return {
            "state":                  "CATEGORY_INPUT",
            "duration":               self.CATEGORY_INPUT_SECONDS,
            "ends_at":                self._iso(self._input_ends_at) if self._input_ends_at else None,
            "player_options":         self._player_options_payload(),
            "inspiration_categories": self.inspiration_categories,
            "players_ranked":         self._ranked(),
            "submitted":              list(self.player_categories.keys()),
        }

    def _sync_payload_generating(self) -> dict:
        return {
            "state":    "GENERATING",
            "progress": self._gen_progress,
            "total":    self._gen_total,
        }

    def sync_tv_state(self, sid: str):
        s = self.state
        if s == "CATEGORY_INPUT":
            self.socketio.emit("yc_category_input", self._sync_payload_input(), to=sid)
        elif s in ("GENERATING", "FINALIZING", "ANNOUNCEMENT"):
            self.socketio.emit("yc_generating", self._sync_payload_generating(), to=sid)
        elif s in ("QUESTION_INTRO", "OPEN_ANSWERS", "CLOSE_ANSWERS",
                   "REVEAL", "UNVEIL", "RESOLUTION", "SCORING"):
            if self._current_q_payload:
                self.socketio.emit("show_question", self._current_q_payload, to=sid)

    def sync_controller_state(self, sid: str):
        s = self.state
        if s == "CATEGORY_INPUT":
            self.socketio.emit("yc_category_input", self._sync_payload_input(), to=sid)
        elif s in ("GENERATING", "FINALIZING", "ANNOUNCEMENT"):
            self.socketio.emit("yc_generating", self._sync_payload_generating(), to=sid)
        elif s in ("QUESTION_INTRO", "OPEN_ANSWERS", "CLOSE_ANSWERS",
                   "REVEAL", "UNVEIL", "RESOLUTION", "SCORING"):
            if self._current_q_payload:
                self.socketio.emit("show_question", self._current_q_payload, to=sid)

    # -----------------------------------------------------------------------
    # FINISH
    # -----------------------------------------------------------------------

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        self.state = "DONE"
        if callable(self.on_game_finished):
            self.on_game_finished()
