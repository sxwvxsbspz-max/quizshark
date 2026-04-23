import os
import random
import threading
from datetime import datetime, timezone

from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc
from engine.ranking import get_players_ranked
from engine.audio.resolve_audio import resolve_audio_ref

# ---------- Konfiguration ----------
POINTS_CORRECT       = 50
MAX_ROUNDS           = 15
ANCHOR_YEAR_MARGIN   = 10   # Ausgangsjahr: frühestens ältester+10, spätestens neuester-10

TIMING_INTRO         = 3.0   # show_question → open_answers
TIMING_ANSWER        = 28.0  # Antwortzeit
TIMING_REVEAL        = 2.0   # close_answers → reveal_player_answers
TIMING_UNVEIL        = 1.5   # reveal → unveil_correct
TIMING_RESOLUTION    = 1.2   # unveil → show_resolution
TIMING_SCORING       = 3.0   # show_resolution → show_scoring
TIMING_SCORE_UPDATE  = 2.0   # show_scoring → apply_scoring_update
TIMING_NEXT_ROUND    = 2.0   # apply_scoring_update → nächste Runde

APPLE_HARD_DELETE    = {"itunes_no_preview", "itunes_no_results"}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)

def _safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0

def _sort_timeline(tiles):
    return sorted(tiles, key=lambda t: _safe_int(t["year"]))

def _compute_year_range(slot_index, sorted_timeline):
    """Jahresspanne basierend auf Einordnungsposition."""
    years = [_safe_int(t["year"]) for t in sorted_timeline]
    n = len(years)
    if n == 0:
        return "—"
    if slot_index <= 0:
        return f"< {years[0]}"
    if slot_index >= n:
        return f"> {years[-1]}"
    return f"{years[slot_index - 1]}–{years[slot_index]}"

def _is_correct_placement(slot_index, song_year, sorted_timeline):
    """True wenn song_year chronologisch korrekt an dieser Stelle liegt."""
    years = [_safe_int(t["year"]) for t in sorted_timeline]
    n = len(years)
    if n == 0:
        return True
    if slot_index <= 0:
        return song_year < years[0]
    if slot_index >= n:
        return song_year > years[-1]
    return years[slot_index - 1] < song_year < years[slot_index]


# ---------------------------------------------------------------------------
# Fragen-Auswahl
# ---------------------------------------------------------------------------

class SongsterQuestionSource:
    def __init__(self, questions_path):
        self.questions_path  = questions_path
        self.base_dir        = os.path.dirname(os.path.abspath(questions_path))
        self.play_log_path   = os.path.join(self.base_dir, "play_log.txt")
        self.cleanup_log_path = os.path.join(self.base_dir, "audio_cleanup_log.txt")

    def _log_play(self, q, status, reason=""):
        try:
            detail = f" ({reason})" if reason else ""
            line = (f"[{_utc_iso()}] {status:<8} id={q.get('id','?')} "
                    f"{q.get('year','')}  {q.get('artist','')} – {q.get('title','')}{detail}\n")
            with open(self.play_log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _log_cleanup(self, q, provider, reason):
        try:
            lines = [
                f"[{_utc_iso()}]", f"REASON: {reason}", f"PROVIDER: {provider}",
                f"QUESTION_ID: {q.get('id')}", "",
                f"TITLE: {q.get('title')}", f"ARTIST: {q.get('artist')}",
                f"YEAR: {q.get('year')}", "-" * 50, "",
            ]
            with open(self.cleanup_log_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception:
            pass

    def get_year_range(self):
        questions = load_json_questions(self.questions_path)
        years = [_safe_int(q.get("year")) for q in (questions or []) if _safe_int(q.get("year")) > 0]
        if not years:
            return (1970, 2020)
        return (min(years), max(years))

    def next_question(self, played_years: set, anchor_year: int):
        questions = load_json_questions(self.questions_path)
        if not questions:
            return None

        eligible = [
            q for q in questions
            if q.get("year") and
               _safe_int(q["year"]) not in played_years and
               _safe_int(q["year"]) != anchor_year
        ]
        if not eligible:
            return None

        max_tries = 30
        tried_ids = set()

        for _ in range(max_tries):
            unplayed = [q for q in eligible if not q.get("lastplayed")]
            if len(unplayed) > 5:
                random.shuffle(unplayed)
                pool = unplayed[:5]
            else:
                eligible.sort(key=lambda q: (lastplayed_ts(q), _safe_int(q.get("id", 0))))
                pool = eligible[:5] if len(eligible) > 5 else eligible[:]

            pool = [q for q in pool if q.get("id") not in tried_ids] or pool
            if not pool:
                return None

            q = random.choice(pool)
            tried_ids.add(q.get("id"))

            resolved = resolve_audio_ref(
                q.get("audio"),
                title=q.get("title"),
                artist=q.get("artist"),
                year=q.get("year") if q.get("year") not in ("", None) else None,
                local_audio_base_url="/songster/media/audio",
                allow_passthrough_urls=True,
            )

            if not (resolved and resolved.ok and resolved.url):
                provider = getattr(resolved, "provider", "none") if resolved else "none"
                reason   = (getattr(resolved, "reason", None) if resolved else None) or "audio_unresolved"
                if provider == "itunes" and reason in APPLE_HARD_DELETE:
                    self._log_cleanup(q, provider, reason)
                    self._log_play(q, "DELETED", reason)
                    qid = q.get("id")
                    all_qs = [qq for qq in load_json_questions(self.questions_path) if qq.get("id") != qid]
                    save_json_questions(self.questions_path, all_qs)
                    eligible = [qq for qq in eligible if qq.get("id") != qid]
                else:
                    self._log_play(q, "ERROR", reason)
                continue

            # Als gespielt markieren
            q["lastplayed"] = now_iso_utc()
            all_qs = load_json_questions(self.questions_path)
            for qq in all_qs:
                if qq.get("id") == q.get("id"):
                    qq["lastplayed"] = q["lastplayed"]
                    break
            save_json_questions(self.questions_path, all_qs)
            self._log_play(q, "OK")

            year_val = _safe_int(q.get("year"))
            if year_val == 0 and getattr(resolved, "resolved_year", None):
                year_val = _safe_int(resolved.resolved_year)

            return {
                "id":     q.get("id"),
                "audio":  resolved.url,
                "year":   year_val,
                "title":  q.get("title"),
                "artist": q.get("artist"),
            }

        return None


# ---------------------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------------------

class SongsterLogic:
    """
    Hitster-Mechanik:
    - Ausgangsjahr (Anker) zufällig generiert
    - Spieler ordnen Songs per Drag & Drop chronologisch ein
    - Pro Spieler eigene Timeline (nur korrekte Einordnungen bleiben sichtbar)
    - TV zeigt gemeinsame Timeline mit allen korrekt platzierten Songs
    """

    def __init__(self, socketio, players, on_game_finished=None):
        self.socketio          = socketio
        self.players           = players          # dict: player_id → {name, score, ...}
        self.on_game_finished  = on_game_finished

        questions_path  = os.path.join(os.path.dirname(__file__), "questions.json")
        self.source     = SongsterQuestionSource(questions_path)

        # Spielzustand
        self.state             = "idle"           # idle → video → question_intro → answers_open → ...
        self.current_round     = 0
        self.anchor_year       = None
        self.played_years      = set()
        self.tv_timeline       = []               # [{year, is_anchor, title, artist}], sortiert
        self.player_timelines  = {}               # player_id → [{...}], sortiert
        self.current_q         = None             # {id, audio, year, title, artist}
        self.player_slots      = {}               # player_id → slot_index (aktuelle Runde)
        self._last_results     = {}               # player_id → {correct, slot_index}
        self._timers           = []

        for pid in self.players:
            self.player_timelines[pid] = []

        self._init_anchor()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_anchor(self):
        min_y, max_y = self.source.get_year_range()
        lo = min_y + ANCHOR_YEAR_MARGIN
        hi = max_y - ANCHOR_YEAR_MARGIN
        if lo >= hi:
            lo, hi = min_y, max_y
        self.anchor_year = random.randint(lo, hi)
        anchor_tile = {"year": self.anchor_year, "is_anchor": True, "title": None, "artist": None}
        self.tv_timeline = [anchor_tile]
        for pid in self.player_timelines:
            self.player_timelines[pid] = [dict(anchor_tile)]

    # ------------------------------------------------------------------
    # Timer helpers
    # ------------------------------------------------------------------

    def _after(self, delay, fn, *args):
        t = threading.Timer(delay, fn, args=args)
        t.daemon = True
        self._timers.append(t)
        t.start()
        return t

    def _cancel_timers(self):
        for t in self._timers:
            try:
                t.cancel()
            except Exception:
                pass
        self._timers.clear()

    # ------------------------------------------------------------------
    # Emit helpers
    # ------------------------------------------------------------------

    def _emit_all(self, event, data):
        self.socketio.emit(event, data, room="tv_room")
        self.socketio.emit(event, data, room="controller_room")

    def _players_ranked(self):
        return get_players_ranked(self.players)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def sync_controller_state(self, sid):
        if self.state in ("question_intro", "answers_open", "revealing", "resolution", "scoring"):
            if self.current_q:
                self.socketio.emit("show_question", self._question_payload(), to=sid)
        if self.state == "answers_open":
            self.socketio.emit("open_answers", {"duration": TIMING_ANSWER}, to=sid)
        if self.state in ("revealing", "resolution", "scoring"):
            self.socketio.emit("close_answers", {}, to=sid)

    def handle_event(self, player_id, action, payload):
        if action == "video_finished":
            if self.state == "idle":
                # Intro-Video abgespielt → erste Runde
                self._start_round()
            elif self.state == "video":
                # Runden-Video abgespielt → Frage anzeigen
                self._show_question()

        elif action == "submit_answer" and self.state == "answers_open" and player_id:
            self._on_submit(player_id, payload or {})

    def get_players_ranked(self):
        return self._players_ranked()

    # ------------------------------------------------------------------
    # Spielfluss
    # ------------------------------------------------------------------

    def _start_round(self):
        if self.current_round >= MAX_ROUNDS:
            self._finish_game()
            return

        self.current_round += 1
        self.player_slots  = {}
        self._last_results = {}
        self.state = "video"
        self._emit_all("play_round_video", {"round": self.current_round})

    def _show_question(self):
        q = self.source.next_question(self.played_years, self.anchor_year)
        if q is None:
            self._finish_game()
            return

        self.current_q = q
        self.state = "question_intro"
        self._emit_all("show_question", self._question_payload())
        self._after(TIMING_INTRO, self._open_answers)

    def _open_answers(self):
        if self.state != "question_intro":
            return
        self.state = "answers_open"
        started_at = _now_ms()
        self._emit_all("open_answers", {
            "duration":   TIMING_ANSWER,
            "started_at": started_at,
        })
        self._after(TIMING_ANSWER, self._close_answers)

    def _on_submit(self, player_id, payload):
        if player_id in self.player_slots:
            return
        slot = int(payload.get("slot_index", 0))
        self.player_slots[player_id] = slot
        self._emit_all("player_logged_in", {"player_id": player_id})

        if len(self.player_slots) >= len(self.players):
            self._cancel_timers()
            self._close_answers()

    def _close_answers(self):
        if self.state != "answers_open":
            return
        # Spieler ohne Antwort: Slot 0 (ganz oben = ältester)
        for pid in self.players:
            if pid not in self.player_slots:
                self.player_slots[pid] = 0
        self.state = "revealing"
        self._emit_all("close_answers", {})
        self._after(TIMING_REVEAL, self._reveal_answers)

    def _reveal_answers(self):
        answers = {}
        for pid, slot in self.player_slots.items():
            tl = _sort_timeline(self.player_timelines.get(pid, []))
            answers[pid] = {
                "slot_index": slot,
                "year_range": _compute_year_range(slot, tl),
            }
        self._emit_all("reveal_player_answers", {"player_answers": answers})
        self._after(TIMING_UNVEIL, self._unveil_correct)

    def _unveil_correct(self):
        q = self.current_q
        self._emit_all("unveil_correct", {
            "correct_year": q["year"],
            "title":        q["title"],
            "artist":       q["artist"],
        })
        self._after(TIMING_RESOLUTION, self._show_resolution)

    def _show_resolution(self):
        q     = self.current_q
        q_year = q["year"]

        # Ergebnisse bewerten
        player_results = {}
        for pid, slot in self.player_slots.items():
            tl = _sort_timeline(self.player_timelines.get(pid, []))
            correct = _is_correct_placement(slot, q_year, tl)
            player_results[pid] = {"correct": correct, "slot_index": slot}
        self._last_results = player_results

        # Song-Tile für alle Timelines anlegen
        new_tile = {"year": q_year, "is_anchor": False, "title": q["title"], "artist": q["artist"]}

        # TV-Timeline: Song immer hinzufügen
        self.tv_timeline = _sort_timeline(self.tv_timeline + [dict(new_tile)])
        self.played_years.add(q_year)

        # Spieler-Timelines: nur bei korrekter Einordnung
        for pid, res in player_results.items():
            if res["correct"]:
                self.player_timelines[pid] = _sort_timeline(
                    self.player_timelines[pid] + [dict(new_tile)]
                )

        self.state = "resolution"
        self._emit_all("show_resolution", {
            "correct_year":     q_year,
            "title":            q["title"],
            "artist":           q["artist"],
            "player_results":   player_results,
            "tv_timeline":      self.tv_timeline,
            "player_timelines": self.player_timelines,
        })
        self._after(TIMING_SCORING, self._show_scoring)

    def _show_scoring(self):
        q_year = self.current_q["year"]
        gained = {}

        for pid in self.players:
            res = self._last_results.get(pid, {})
            gained[pid] = POINTS_CORRECT if res.get("correct") else 0

        ranked_before = self._players_ranked()

        for pid, pts in gained.items():
            if pts > 0 and pid in self.players:
                self.players[pid]["score"] = int(self.players[pid].get("score", 0)) + pts

        ranked_after = self._players_ranked()

        self.state = "scoring"
        self._emit_all("show_scoring", {
            "gained":         gained,
            "players_ranked": ranked_before,
            "show_pop":       True,
        })
        self._after(TIMING_SCORE_UPDATE, self._apply_scoring_update, ranked_after)

    def _apply_scoring_update(self, ranked_after):
        self._emit_all("apply_scoring_update", {"players_ranked": ranked_after})
        self._after(TIMING_NEXT_ROUND, self._start_round)

    def _finish_game(self):
        self.state = "idle"
        if self.on_game_finished:
            self.on_game_finished()

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------

    def _question_payload(self):
        return {
            "round":             self.current_round,
            "audio":             self.current_q["audio"] if self.current_q else None,
            "anchor_year":       self.anchor_year,
            "tv_timeline":       self.tv_timeline,
            "player_timelines":  self.player_timelines,
            "players_ranked":    self._players_ranked(),
        }
