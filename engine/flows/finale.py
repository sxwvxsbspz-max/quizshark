# --- FILE: ./engine/flows/finale.py ---


from __future__ import annotations

import threading  # bleibt importiert, wird aber nicht mehr fuer Timer genutzt
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

# Wir übernehmen StandardQuizTiming aus dem Standard-Flow-Modul
# (damit du in finale/logic.py weiterhin StandardQuizTiming(...) nutzen kannst)
from engine.flows.mc_standard import StandardQuizTiming  # type: ignore


def _utc_ms() -> int:
    return int(time.time() * 1000)


class FinaleFlow:
    def __init__(
        self,
        core,
        *,
        max_rounds: int = 9999,
        timing: Optional[StandardQuizTiming] = None,
        scoring=None,
        answer_type=None,
        question_source=None,
    ):
        self.core = core
        self.max_rounds = int(max_rounds or 9999)

        self.timing = timing or StandardQuizTiming(
            intro_delay_seconds=3,
            answer_duration_seconds=15,
            reveal_answers_seconds=3,
            resolution_seconds=2,
            scoring_show_points_seconds=2,
            scoring_hold_after_update_seconds=2,
        )

        # scoring bleibt optional – wir nutzen es nur, um gained=0 zu erzeugen,
        # aber wir erhöhen die Punkte NICHT.
        self.scoring = scoring
        self.answer_type = answer_type
        self.question_source = question_source

        # State
        self.round_index = 0
        self.phase = "idle"  # idle|pause|question|open|reveal|unveil|resolution|resolution_wait_tv|finished

        self.current_question: Optional[dict] = None
        self.current_answers: Dict[str, Optional[int]] = {}  # pid -> choice int or None
        self.answered_flag: Dict[str, bool] = {}            # pid -> bool (nur aktive)

        # (Legacy-Feld bleibt, ist aber nicht mehr die primäre Quelle)
        self.started_at_ms: Optional[int] = None

        # NEU (Punktesammler-Konzept): absolute Zeitpunkte (UTC)
        self._round_token: int = 0

        self._question_shown_at: Optional[datetime] = None
        self._question_shown_at_iso: Optional[str] = None

        self._answers_unveil_at: Optional[datetime] = None
        self._answers_unveil_at_iso: Optional[str] = None

        self._open_answers_started_at: Optional[datetime] = None
        self._open_answers_started_at_iso: Optional[str] = None
        self._open_answers_duration: Optional[float] = None  # seconds

        # Reconnect/State: Merker, ob unveil_correct bereits gesendet wurde
        self._correct_unveiled: bool = False

        # Meta für UI
        self.white_used: set[str] = set()
        self.gold_used: set[str] = set()
        self.eliminated_this_q: set[str] = set()

        # NEU: Screen-Liste (pre-elimination), damit survivors NICHT neu gerendert werden bis nächste Frage
        self._players_ranked_screen: list[dict] = []
        self._screen_order_pids: list[str] = []

        # NEU: Elimination-Sequenz Defaults (TV nutzt das als Timing/Assets-Hint)
        self.elimination_pause_ms: int = 1000
        self.elimination_stagger_ms: int = 250
        self.elimination_announcement_audio: str = "eliminated_announcement.mp3"
        self.elimination_tile_audio: str = "eliminated.mp3"

        # NEU: Finale wartet nach resolution auf TV-ACK
        self.wait_for_tv_ack: bool = True

        # NEU: Sofortpause (nur an Safe-Points wirksam; check passiert vor StartNextQuestion)
        self._sofortpause_requested: bool = False
        self._pause_resume_target: Optional[str] = None

        # Timer handles (bleiben als Attribute bestehen, werden aber nicht mehr genutzt)
        self._t_intro: Optional[threading.Timer] = None
        self._t_close: Optional[threading.Timer] = None
        self._t_reveal: Optional[threading.Timer] = None
        self._t_unveil: Optional[threading.Timer] = None
        self._t_resolution: Optional[threading.Timer] = None
        self._t_scoring_show: Optional[threading.Timer] = None
        self._t_scoring_apply: Optional[threading.Timer] = None

    # -----------------------------
    # Utilities: players / ranking
    # -----------------------------
    def _players(self) -> Dict[str, dict]:
        return self.core.players or {}

    def _is_active(self, pid: str) -> bool:
        p = (self._players().get(pid) or {})
        return not bool(p.get("is_eliminated", False))

    def _active_player_ids(self):
        return [pid for pid in self._players().keys() if self._is_active(pid)]

    def _active_count(self) -> int:
        return len(self._active_player_ids())

    def _reset_answer_state_for_new_question(self):
        self.current_answers = {}
        self.answered_flag = {}
        self.white_used = set()
        self.gold_used = set()
        self.eliminated_this_q = set()

        # Reset unveil marker
        self._correct_unveiled = False

        for pid in self._active_player_ids():
            self.current_answers[pid] = None
            self.answered_flag[pid] = False
            # answered-flag im global players-dict (falls Controller das nutzt)
            p = self._players().get(pid) or {}
            p["answered"] = False

    def _sort_key(self, pid: str):
        p = self._players().get(pid) or {}
        w = int(p.get("jokers_white", 0) or 0)
        g = int(p.get("jokers_gold", 0) or 0)
        score = int(p.get("score", 0) or 0)
        total = w + g
        # desc sort => negative values
        # NEU/GLATT: Gold vor Total ist gewollt
        return (-g, -total, -score, (p.get("name") or "").lower(), pid)

    def players_ranked(self):
        """
        Liefert NUR aktive Spieler (eliminiert raus),
        sortiert nach jokers_gold, jokers_total, score.
        """
        items = []
        for pid in self._active_player_ids():
            p = self._players().get(pid) or {}
            items.append(
                {
                    "player_id": pid,
                    "name": (p.get("name") or ""),
                    "score": int(p.get("score", 0) or 0),
                    "jokers_white": int(p.get("jokers_white", 0) or 0),
                    "jokers_gold": int(p.get("jokers_gold", 0) or 0),
                }
            )

        items.sort(key=lambda it: self._sort_key(it["player_id"]))

        # rankdisplay = 1..N (nur Anzeige; echte "rank ties" sind hier nicht zentral)
        for i, it in enumerate(items):
            it["rankdisplay"] = i + 1
            it["rank"] = i + 1
        return items

    # -----------------------------
    # Timing helpers (Punktesammler-Konzept)
    # -----------------------------
    def _iso_utc(self, dt: Optional[datetime]) -> Optional[str]:
        if not isinstance(dt, datetime):
            return None
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _remaining_open_seconds(self) -> float:
        dur = float(self._open_answers_duration or float(self.timing.answer_duration_seconds or 0))
        if not self._open_answers_started_at:
            return dur
        elapsed = (datetime.now(timezone.utc) - self._open_answers_started_at).total_seconds()
        return max(0.0, dur - float(elapsed))

    # -----------------------------
    # Emit helpers
    # -----------------------------
    def _tv_emit(self, event: str, payload: dict):
        self.core.socketio.emit(event, payload, room="tv_room")

    def _ctrl_emit(self, event: str, payload: dict):
        self.core.socketio.emit(event, payload, room="controller_room")

    def _emit_both(self, event: str, payload: dict):
        self._tv_emit(event, payload)
        self._ctrl_emit(event, payload)

    # -----------------------------
    # Pause helpers (wie MCStandardFlow)
    # -----------------------------
    def _emit_show_pause(self, to: Optional[str] = None):
        payload = {"mode": "sofortpause"}
        if to:
            self.core.socketio.emit("show_pause", payload, to=to)
            return
        self.core.socketio.emit("show_pause", payload, room="tv_room")
        self.core.socketio.emit("show_pause", payload, room="controller_room")

    def _emit_hide_pause(self, to: Optional[str] = None):
        if to:
            self.core.socketio.emit("hide_pause", {}, to=to)
            return
        self.core.socketio.emit("hide_pause", {}, room="tv_room")
        self.core.socketio.emit("hide_pause", {}, room="controller_room")

    def _enter_pause(self, resume_target: str):
        # Sofortpause wird "konsumiert" beim Eintritt
        self._sofortpause_requested = False
        self._pause_resume_target = str(resume_target or "START_NEXT_QUESTION")
        self.phase = "pause"
        self._emit_show_pause()

    def _resume_from_pause(self):
        self._emit_hide_pause()
        target = self._pause_resume_target or "START_NEXT_QUESTION"
        self._pause_resume_target = None

        # WICHTIG: erst aus der Pause raus, sonst blockt start_next_question()
        if self.phase == "pause":
            self.phase = "idle"

        # Default: weiter wie "nächster Schritt"
        if target == "START_NEXT_QUESTION":
            self.start_next_question()
            return

        # Fallback
        self.start_next_question()

    # -----------------------------
    # Flow entrypoints
    # -----------------------------
    def handle_event(self, player_id: Optional[str], action: str, payload: dict):
        payload = payload or {}

        # NEU: Sofortpause toggle (admin/system) – wirkt am Safe-Point (vor StartNextQuestion)
        if action == "request_pause":
            if self.phase == "pause":
                return
            self._sofortpause_requested = True
            return

        if action == "resume_pause":
            if self.phase == "pause":
                self._resume_from_pause()
            return

        # System actions
        if player_id is None:
            if action == "video_finished":
                # Finale startet nach Video automatisch die erste Frage
                if self.phase in ("idle", "finished"):
                    self.start_next_question()
                return

            # NEU: TV bestätigt, dass Resolution-Animation/Sounds fertig sind
            if action == "resolution_finished":
                # optional: round-check
                try:
                    r = payload.get("round", None)
                    if r is not None and int(r) != int(self.round_index):
                        return
                except Exception:
                    pass

                if self.phase == "resolution_wait_tv":
                    # weiter wie früher: Ende prüfen / nächste Frage
                    if self._active_count() <= 1 or self.round_index >= self.max_rounds:
                        self._finish_module()
                    else:
                        self.start_next_question()
                return

            if action == "timer_expired":
                # optional (falls dein Frontend sowas auslöst) -> wie close
                if self.phase == "open":
                    self._close_answers_and_reveal(reason="timer_expired")
                return

            if action == "module_finished":
                self._finish_module()
                return

            return

        # Player actions
        if action in ("submit_answer", "answer", "submit"):
            self._on_submit_answer(player_id, payload)
            return

        # Unknown -> ignore
        return

    # -----------------------------
    # Core flow steps (Punktesammler-Konzept)
    # -----------------------------
    def start_next_question(self):
        if self.phase == "finished":
            return

        # NEU: Safe-Point – Pause greift HIER, bevor eine neue Frage startet
        if self._sofortpause_requested:
            self._enter_pause(resume_target="START_NEXT_QUESTION")
            return

        # Wenn wir (aus irgendeinem Grund) noch in pause stehen und jemand "start_next_question" indirekt triggert:
        if self.phase == "pause":
            return

        # Ende, wenn <= 1 aktiv oder max_rounds erreicht
        if self._active_count() <= 1 or self.round_index >= self.max_rounds:
            self._finish_module()
            return

        self.round_index += 1
        self.phase = "question"

        # Token hochzählen => alle alten Tasks werden inert
        self._round_token += 1
        token = self._round_token

        # Frage holen (WICHTIG: round_index durchreichen, sonst bleibt difficulty immer "easy")
        q = (
            self.question_source.next_question(round_index=self.round_index)
            if self.question_source
            else None
        )
        if not q:
            self._finish_module()
            return

        self.current_question = q
        self._reset_answer_state_for_new_question()

        # NEU: Screen-Liste fixieren (pre-elimination) für diese Frage
        self._players_ranked_screen = self.players_ranked()
        self._screen_order_pids = [it.get("player_id") for it in (self._players_ranked_screen or []) if it.get("player_id")]

        # absolute Zeitpunkte wie MCStandardFlow
        now = datetime.now(timezone.utc)
        self._question_shown_at = now
        self._question_shown_at_iso = self._iso_utc(now)

        unveil_at = now + timedelta(seconds=float(self.timing.intro_delay_seconds or 0))
        self._answers_unveil_at = unveil_at
        self._answers_unveil_at_iso = self._iso_utc(unveil_at)

        # (legacy started_at_ms reset)
        self.started_at_ms = None
        self._open_answers_started_at = None
        self._open_answers_started_at_iso = None
        self._open_answers_duration = None

        data = {
            "round": self.round_index,
            "text": q.get("text") or "",
            "options": q.get("options") or [],
            "correct_index": int(q.get("correct_index", 0) or 0),
            "audio": q.get("audio"),
            "image": q.get("image"),
            "players_ranked": self._players_ranked_screen,

            # Punktesammler-Konzept: absolute Zeitpunkte (ISO)
            "question_shown_at": self._question_shown_at_iso,
            "answers_unveil_at": self._answers_unveil_at_iso,
        }

        self._emit_both("show_question", data)

        # intro-delay -> open_answers
        self.core.start_task(self._open_answers_after_delay, token)

    def _open_answers_after_delay(self, token: int):
        self.core.sleep(float(self.timing.intro_delay_seconds or 0))
        if token != self._round_token or self.phase != "question":
            return
        self._open_answers(token)

    def _open_answers(self, token: int):
        if token != self._round_token or self.phase != "question":
            return

        self.phase = "open"

        self._open_answers_started_at = datetime.now(timezone.utc)
        self._open_answers_started_at_iso = self._iso_utc(self._open_answers_started_at)
        self._open_answers_duration = float(self.timing.answer_duration_seconds or 0)

        # legacy ms (nur als Nebeninfo)
        self.started_at_ms = _utc_ms()

        dur = float(self._open_answers_duration or 0)

        self._emit_both(
            "open_answers",
            {
                "duration": float(dur),
                "started_at": self._open_answers_started_at_iso,
                "round": self.round_index,
                "total_duration": float(dur),
                "remaining": float(dur),

                # optional/harmlos: ms for debugging / alte clients
                "started_at_ms": self.started_at_ms,
            },
        )

        # close nach duration
        self.core.start_task(self._answer_timer_task, token, float(dur))

    def _answer_timer_task(self, token: int, seconds: float):
        self.core.sleep(float(seconds))
        if token != self._round_token or self.phase != "open":
            return
        self._close_answers_and_reveal(reason="timer")

    def _close_answers_and_reveal(self, reason: str = ""):
        if self.phase != "open":
            return

        # Token erhöhen: killt open-timer-task deterministisch (wie Punktesammler)
        self._round_token += 1
        token = self._round_token

        self.phase = "reveal"

        self._emit_both("close_answers", {"round": self.round_index, "reason": reason})

        # reveal_player_answers sofort
        self._emit_both(
            "reveal_player_answers",
            {
                "round": self.round_index,
                "player_answers": self._answers_payload_for_ui(),
            },
        )

        # danach unveil_correct nach reveal_answers_seconds
        self.core.start_task(self._unveil_correct_after_delay, token)

    def _unveil_correct_after_delay(self, token: int):
        self.core.sleep(float(self.timing.reveal_answers_seconds or 0))
        if token != self._round_token or self.phase != "reveal":
            return

        self.phase = "unveil"

        correct_idx = int((self.current_question or {}).get("correct_index", 0) or 0)
        self._correct_unveiled = True
        self._emit_both("unveil_correct", {"round": self.round_index, "correct_index": correct_idx})

        # resolution nach resolution_seconds
        self.core.start_task(self._resolution_after_delay, token)

    def _resolution_after_delay(self, token: int):
        self.core.sleep(float(self.timing.resolution_seconds or 0))
        if token != self._round_token or self.phase != "unveil":
            return
        self._show_resolution_and_apply_sudden_death(token)

    def _show_resolution_and_apply_sudden_death(self, token: int):
        if token != self._round_token or self.phase not in ("unveil", "reveal"):
            return

        self.phase = "resolution"

        correct_idx = int((self.current_question or {}).get("correct_index", 0) or 0)

        # sudden death anwenden
        self._apply_sudden_death(correct_idx)

        # NEU: elimination order nach screen order (wie angezeigt)
        ordered_eliminated = [pid for pid in (self._screen_order_pids or []) if pid in self.eliminated_this_q]

        # NEU: Controller informieren, damit eliminated Controller auf "Ausgeschieden :(" wechseln kann
        # (Frontend entscheidet selbst anhand eigener player_id)
        self._ctrl_emit(
            "finale_eliminated",
            {
                "round": self.round_index,
                "eliminated": sorted(list(self.eliminated_this_q)),
                "ordered_eliminated": ordered_eliminated,
            },
        )

        # Resolution an UI senden (inkl. Meta)
        # Wichtig: players_ranked bleibt die SCREEN-LISTE (pre-elimination),
        # damit survivors NICHT neu gerendert werden bis zur nächsten Frage.
        self._emit_both(
            "show_resolution",
            {
                "round": self.round_index,
                "correct_index": correct_idx,
                "player_answers": self._answers_payload_for_ui(),
                "players_ranked": (self._players_ranked_screen or []),  # pre-elim screen list
                "players_ranked_next": self.players_ranked(),           # post-elim (survivors) für nächste Frage
                "finale_meta": {
                    "white_used": sorted(list(self.white_used)),
                    "gold_used": sorted(list(self.gold_used)),
                    "eliminated": sorted(list(self.eliminated_this_q)),
                    "ordered_eliminated": ordered_eliminated,
                    "elimination_sequence": {
                        "pause_ms": int(self.elimination_pause_ms),
                        "stagger_ms": int(self.elimination_stagger_ms),
                        "announcement_audio": self.elimination_announcement_audio,
                        "tile_audio": self.elimination_tile_audio,
                    },
                },
            },
        )

        # Scoring-Phasen bleiben kompatibel, aber ohne Punkte-Erhöhung.
        # NEU: Standard ist: warten auf TV-ACK (resolution_finished)
        if self.wait_for_tv_ack:
            self.phase = "resolution_wait_tv"
            return

        # Fallback (wenn wait_for_tv_ack abgeschaltet wird):
        self.core.start_task(self._show_scoring_zero_after_delay, token)

    def _show_scoring_zero_after_delay(self, token: int):
        self.core.sleep(float(self.timing.scoring_show_points_seconds or 0))
        if token != self._round_token or self.phase != "resolution":
            return
        self._show_scoring_zero(token)

    def _show_scoring_zero(self, token: int):
        # gained = 0 für alle aktiven (oder auch alle) – anyPoints bleibt false in tv.js
        gained = {}
        for pid in self._active_player_ids():
            gained[pid] = 0

        self._emit_both(
            "show_scoring",
            {
                "round": self.round_index,
                "gained": gained,
                "players_ranked": self.players_ranked(),
            },
        )

        self.core.start_task(self._apply_scoring_update_after_delay, token)

    def _apply_scoring_update_after_delay(self, token: int):
        self.core.sleep(float(self.timing.scoring_hold_after_update_seconds or 0))
        if token != self._round_token or self.phase != "resolution":
            return
        self._apply_scoring_update_noop(token)

    def _apply_scoring_update_noop(self, token: int):
        # keine Score-Änderung, aber event senden für Frontend-Flow
        self._emit_both(
            "apply_scoring_update",
            {"round": self.round_index, "players_ranked": self.players_ranked()},
        )

        # Ende prüfen / nächste Frage starten
        if self._active_count() <= 1 or self.round_index >= self.max_rounds:
            self._finish_module()
        else:
            self.start_next_question()

    def _finish_module(self):
        self.phase = "finished"

        # optional: wenn du ein spezielles Finale-Ende-Event willst, kannst du hier eins emitten.
        # Wir nutzen das Callback, damit app.py -> trigger_next_phase() läuft.
        cb = getattr(self.core, "on_game_finished", None)
        if callable(cb):
            try:
                cb()
            except Exception:
                pass

    # -----------------------------
    # Answer submission
    # -----------------------------
    def _on_submit_answer(self, player_id: str, payload: dict):
        if self.phase != "open":
            return
        if not self._is_active(player_id):
            return

        p = self._players().get(player_id) or {}
        if bool(p.get("answered", False)):
            return

        # Erwartung: payload enthält "choice" oder "value"
        raw = payload.get("choice", payload.get("value", payload.get("answer", None)))
        try:
            choice = int(raw) if raw is not None else None
        except Exception:
            choice = None

        # White = 4
        if choice == 4:
            # Sicherheitsgurt: wenn kein White (sollte nicht vorkommen) -> merken, aber am Ende "raus"
            w = int(p.get("jokers_white", 0) or 0)
            if w > 0:
                p["jokers_white"] = w - 1
                self.white_used.add(player_id)
            else:
                # keine White verfügbar -> markieren und als "invalid white" behandeln
                # Wir lassen choice==4 stehen; sudden-death wird ihn eliminieren.
                pass

        # Speichern
        self.current_answers[player_id] = choice
        self.answered_flag[player_id] = True
        p["answered"] = True

        # TV sfx/mark answered
        self._tv_emit("player_logged_in", {"player_id": player_id})

        # Early close, wenn alle aktiven geantwortet haben
        if self._all_active_answered():
            # deterministisch wie Punktesammler: Token invalidieren und direkt weiter
            self._close_answers_and_reveal(reason="all_answered")

    def _all_active_answered(self) -> bool:
        for pid in self._active_player_ids():
            if not bool(self.answered_flag.get(pid, False)):
                return False
        return True

    # -----------------------------
    # Sudden death application
    # -----------------------------
    def _apply_sudden_death(self, correct_idx: int):
        self.eliminated_this_q = set()
        # gold_used/white_used sind bereits sets; white_used wird beim Submit gesetzt,
        # gold_used erst hier.

        for pid in list(self._active_player_ids()):
            p = self._players().get(pid) or {}
            choice = self.current_answers.get(pid, None)

            # White (4) -> korrekt (falls w==0 "cheat" => raus)
            if choice == 4:
                w_now = int(p.get("jokers_white", 0) or 0)
                # Wenn er "cheatet" und hatte keinen White, dann ist er raus.
                # (Da wir beim Submit nur dann abziehen, wenn w>0, kann man so sauber erkennen)
                # Heuristik: wenn pid NICHT in white_used, dann war es ein invalid white.
                if pid not in self.white_used:
                    p["is_eliminated"] = True
                    self.eliminated_this_q.add(pid)
                else:
                    # korrekt -> bleibt drin
                    pass
                continue

            # Normal choice
            is_correct = (choice is not None) and (int(choice) == int(correct_idx))

            if is_correct:
                continue

            # falsch oder keine Antwort -> Gold ziehen oder raus
            g = int(p.get("jokers_gold", 0) or 0)
            if g > 0:
                p["jokers_gold"] = g - 1
                self.gold_used.add(pid)
            else:
                p["is_eliminated"] = True
                self.eliminated_this_q.add(pid)

        # Survivor counter hochzählen (nur wer nach dem Apply noch aktiv ist)
        for pid in self._active_player_ids():
            p = self._players().get(pid) or {}
            p["final_rounds_survived"] = int(p.get("final_rounds_survived", 0) or 0) + 1

    # -----------------------------
    # UI payload helpers
    # -----------------------------
    def _answers_payload_for_ui(self) -> Dict[str, Optional[int]]:
        """
        TV erwartet player_answers als pid->choice (int).
        Eliminierte sind im Finale UI nicht mehr sichtbar; wir liefern nur aktive + (optional) noch-aktuelle.
        """
        out: Dict[str, Optional[int]] = {}
        for pid in self._players().keys():
            # wir liefern auch eliminated answers mit, schadet nicht – aber UI zeigt sie eh nicht mehr,
            # sobald players_ranked active-only ist.
            out[pid] = self.current_answers.get(pid, None)
        return out

    # -----------------------------
    # Sync (Reconnect)
    # -----------------------------
    def sync_tv_state(self, sid: str):
        """
        Minimaler Sync: Wir senden abhängig von Phase die passenden Events an genau dieses SID.
        """
        # NEU: Pause-State priorisiert
        if self.phase == "pause":
            self._emit_show_pause(to=sid)
            return

        # immer server_time in app.py; hier nur state
        if self.phase == "idle":
            return

        if self.current_question:
            q = self.current_question
            # show_question
            self.core.socketio.emit(
                "show_question",
                {
                    "round": self.round_index,
                    "text": q.get("text") or "",
                    "options": q.get("options") or [],
                    "correct_index": int(q.get("correct_index", 0) or 0),
                    "audio": q.get("audio"),
                    "image": q.get("image"),
                    "players_ranked": (self._players_ranked_screen or self.players_ranked()),

                    # Punktesammler-Konzept: absolute Zeitinfos
                    "question_shown_at": self._question_shown_at_iso,
                    "answers_unveil_at": self._answers_unveil_at_iso,
                },
                to=sid,
            )

        # open_answers nur dann, wenn wir wirklich in OPEN sind
        if self.phase == "open":
            remaining = float(self._remaining_open_seconds())
            total = float(self._open_answers_duration or float(self.timing.answer_duration_seconds or 0))
            self.core.socketio.emit(
                "open_answers",
                {
                    "round": self.round_index,
                    "duration": float(remaining),  # remaining!
                    "started_at": self._open_answers_started_at_iso,
                    "total_duration": float(total),
                    "remaining": float(remaining),

                    # optional/harmlos
                    "started_at_ms": self.started_at_ms,
                },
                to=sid,
            )

        if self.phase in ("reveal", "unveil", "resolution", "resolution_wait_tv"):
            self.core.socketio.emit(
                "reveal_player_answers",
                {"round": self.round_index, "player_answers": self._answers_payload_for_ui()},
                to=sid,
            )

        if self.phase in ("unveil", "resolution", "resolution_wait_tv"):
            if self._correct_unveiled:
                correct_idx = int((self.current_question or {}).get("correct_index", 0) or 0)
                self.core.socketio.emit(
                    "unveil_correct",
                    {"round": self.round_index, "correct_index": correct_idx},
                    to=sid,
                )

        if self.phase in ("resolution", "resolution_wait_tv"):
            correct_idx = int((self.current_question or {}).get("correct_index", 0) or 0)
            ordered_eliminated = [pid for pid in (self._screen_order_pids or []) if pid in self.eliminated_this_q]
            self.core.socketio.emit(
                "show_resolution",
                {
                    "round": self.round_index,
                    "correct_index": correct_idx,
                    "player_answers": self._answers_payload_for_ui(),
                    "players_ranked": (self._players_ranked_screen or []),
                    "players_ranked_next": self.players_ranked(),
                    "finale_meta": {
                        "white_used": sorted(list(self.white_used)),
                        "gold_used": sorted(list(self.gold_used)),
                        "eliminated": sorted(list(self.eliminated_this_q)),
                        "ordered_eliminated": ordered_eliminated,
                        "elimination_sequence": {
                            "pause_ms": int(self.elimination_pause_ms),
                            "stagger_ms": int(self.elimination_stagger_ms),
                            "announcement_audio": self.elimination_announcement_audio,
                            "tile_audio": self.elimination_tile_audio,
                        },
                    },
                },
                to=sid,
            )

    def sync_controller_state(self, sid: str):
        """
        Controller bekommt show_question + open_answers, plus eigene Jokerstände via player-state,
        die der Controller-Client ohnehin aus dem global players dict / separatem sync ziehen kann.
        Wir senden hier (kompatibel) dieselben Events wie an TV, nur an dieses SID.
        """
        # NEU: Pause-State priorisiert
        if self.phase == "pause":
            self._emit_show_pause(to=sid)
            return

        # Für Controller ist das Minimum: show_question + open_answers (wenn offen)
        if self.phase == "idle":
            return

        if self.current_question:
            q = self.current_question
            self.core.socketio.emit(
                "show_question",
                {
                    "round": self.round_index,
                    "text": q.get("text") or "",
                    "options": q.get("options") or [],
                    "audio": q.get("audio"),
                    "image": q.get("image"),
                    "players_ranked": (self._players_ranked_screen or self.players_ranked()),

                    # Punktesammler-Konzept: absolute Zeitinfos
                    "question_shown_at": self._question_shown_at_iso,
                    "answers_unveil_at": self._answers_unveil_at_iso,
                },
                to=sid,
            )

        if self.phase == "open":
            remaining = float(self._remaining_open_seconds())
            total = float(self._open_answers_duration or float(self.timing.answer_duration_seconds or 0))
            self.core.socketio.emit(
                "open_answers",
                {
                    "round": self.round_index,
                    "duration": float(remaining),  # remaining!
                    "started_at": self._open_answers_started_at_iso,
                    "total_duration": float(total),
                    "remaining": float(remaining),

                    # optional/harmlos
                    "started_at_ms": self.started_at_ms,
                },
                to=sid,
            )
