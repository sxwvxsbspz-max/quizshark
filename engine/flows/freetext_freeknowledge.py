# --- FILE: ./engine/flows/freetext_freeknowledge.py ---
# (Wie FreetextStandardFlow, aber für FreeKnowledge:
#  details/accepted werden bereits VOR show_resolution berechnet,
#  damit das TV-Frontend in der Resolution-Phase grün/rot markieren kann.
#  Die Punkte werden trotzdem erst in der Scoring-Phase angewendet.)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, Tuple

from engine.engine_core import EngineCore
from engine.answers.answer_base import AnswerTypeBase
from engine.scoring.scoring_base import ScoringBase


@dataclass
class StandardQuizTiming:
    intro_delay_seconds: float = 3
    answer_duration_seconds: float = 15
    reveal_answers_seconds: float = 3
    resolution_seconds: float = 2
    scoring_show_points_seconds: float = 2
    scoring_hold_after_update_seconds: float = 2
    no_points_hold_seconds: float = 5.0


class FreetextFreeKnowledgeFlow:
    """
    Modul-spezifischer FreeKnowledge-Flow (Freetext).

    Unterschied zu FreetextStandardFlow:
    - Scoring (gained/details) wird bereits vor show_resolution vorbereitet
    - Dadurch enthält show_resolution schon details.accepted
    - Punkte werden trotzdem erst in start_scoring() angewendet
    """

    def __init__(
        self,
        core: EngineCore,
        *,
        max_rounds: int = 1,
        timing: Optional[StandardQuizTiming] = None,
        scoring: Optional[ScoringBase] = None,
        answer_type: Optional[AnswerTypeBase] = None,
        question_source=None,
    ):
        self.core = core

        self.max_rounds = int(max_rounds or 1)
        self.timing = timing or StandardQuizTiming()

        self.scoring: ScoringBase = scoring
        self.answer_type: AnswerTypeBase = answer_type

        self.question_source = question_source

        self.current_round = 0
        self.state = "IDLE"

        self.active_question: Optional[dict] = None

        self.answers: Dict[str, Any] = {}
        self.answer_times: Dict[str, datetime] = {}

        self._round_token = 0

        # Open-Answers Timing
        self._open_answers_started_at: Optional[datetime] = None
        self._open_answers_duration: Optional[float] = None

        # Persistente Snapshots (für Scoring / Reconnect)
        self._last_open_answers_started_at: Optional[datetime] = None
        self._last_open_answers_duration: Optional[float] = None

        # ISO-Strings für Frontend-Resync
        self._open_answers_started_at_iso: Optional[str] = None
        self._last_open_answers_started_at_iso: Optional[str] = None

        # Question / Unveil Timing (absolut)
        self._question_shown_at: Optional[datetime] = None
        self._question_shown_at_iso: Optional[str] = None
        self._answers_unveil_at: Optional[datetime] = None
        self._answers_unveil_at_iso: Optional[str] = None

        # SCORING substates for reconnect
        self._scoring_substate: Optional[str] = None
        self._last_gained: Optional[Dict[str, int]] = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False

        # Zusätzliche Details vom Scoring
        self._last_details: Optional[dict] = None

        # Merker, ob unveil_correct bereits gesendet wurde
        self._correct_unveiled: bool = False

        # Merker: wurden gained/details für diese Runde schon vorbereitet?
        self._resolution_scoring_prepared: bool = False

        # Sofortpause
        self._sofortpause_requested: bool = False
        self._pause_resume_target: Optional[str] = None

    # -------------------------
    # helpers
    # -------------------------

    def players_ranked(self):
        return self.core.players_ranked()

    def _iso_utc(self, dt: Optional[datetime]) -> Optional[str]:
        if not isinstance(dt, datetime):
            return None
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _question_payload(self) -> dict:
        q = self.active_question or {}
        return {
            "text": q.get("text") or q.get("prompt") or "",
            "round": self.current_round,
            "players": self.core.players,
            "players_ranked": self.players_ranked(),
            "audio": q.get("audio"),
            "image": q.get("image"),
            "input_meta": q.get("input_meta") or q.get("meta") or None,
            "question_shown_at": self._question_shown_at_iso,
            "answers_unveil_at": self._answers_unveil_at_iso,
        }

    def _correct_payload(self) -> dict:
        q = self.active_question or {}
        return {
            "correct": q.get("correct"),
            "answer_spec": q.get("answer_spec"),
        }

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
        self._sofortpause_requested = False
        self._pause_resume_target = str(resume_target or "PLAY_NEXT_VIDEO")
        self.state = "PAUSE"
        self._emit_show_pause()

    def _resume_from_pause(self):
        self._emit_hide_pause()
        target = self._pause_resume_target or "PLAY_NEXT_VIDEO"
        self._pause_resume_target = None

        if target == "PLAY_NEXT_VIDEO":
            self.play_next_video()
            return

        if target == "START_QUESTION_INTRO":
            self.start_question_intro()
            return

        self.play_next_video()

    def _unpack_scoring_result(self, res: Any) -> Tuple[Dict[str, int], Optional[dict]]:
        if isinstance(res, tuple) and len(res) == 2:
            gained, details = res
            if gained is None:
                gained = {}
            return dict(gained), (details if isinstance(details, dict) else {"details": details})
        return dict(res or {}), None

    def _compute_scoring_preview(self) -> None:
        """
        Berechnet gained/details genau einmal pro Runde vor der Resolution,
        damit show_resolution schon accepted/details enthält.
        Punkte werden hier NICHT angewendet.
        """
        if self._resolution_scoring_prepared:
            return

        self._players_ranked_before = self.players_ranked()

        res = self.scoring.compute_gained(
            players=self.core.players,
            answers=self.answers,
            question=self.active_question,
            timing={
                "open_started_at": self._last_open_answers_started_at,
                "open_duration": self._last_open_answers_duration,
                "answer_times": self.answer_times,
            },
        )

        gained, details = self._unpack_scoring_result(res)
        self._last_gained = gained
        self._last_details = details
        self._players_ranked_before = self.players_ranked()
        self._resolution_scoring_prepared = True

    # -------------------------
    # reconnect sync (controller)
    # -------------------------

    def sync_controller_state(self, sid: str):
        if self.state == "PAUSE":
            self._emit_show_pause(to=sid)
            return

        if not self.active_question:
            if self.state == "QUESTION_VIDEO":
                self.core.socketio.emit("play_round_video", {"round": self.current_round + 1}, to=sid)
            return

        self.core.socketio.emit(
            "show_question",
            self._question_payload(),
            to=sid,
        )

        if self.state == "QUESTION_OPEN":
            remaining = float(self.timing.answer_duration_seconds)
            started_iso = self._open_answers_started_at_iso
            total = float(self.timing.answer_duration_seconds)

            if self._open_answers_started_at and self._open_answers_duration:
                elapsed = (datetime.now(timezone.utc) - self._open_answers_started_at).total_seconds()
                remaining = max(0.0, float(self._open_answers_duration) - float(elapsed))
                total = float(self._open_answers_duration)

            self.core.socketio.emit(
                "open_answers",
                {
                    "duration": float(remaining),
                    "round": self.current_round,
                    "started_at": started_iso,
                    "total_duration": float(total),
                    "remaining": float(remaining),
                },
                to=sid,
            )

        elif self.state == "REVEAL_ANSWERS":
            self.core.socketio.emit("reveal_player_answers", {"player_answers": self.answers}, to=sid)
            if self._correct_unveiled:
                payload = {}
                payload.update(self._correct_payload())
                self.core.socketio.emit("unveil_correct", payload, to=sid)

        elif self.state in ("RESOLUTION", "NO_POINTS_HOLD"):
            payload = {
                "player_answers": self.answers,
            }
            payload.update(self._correct_payload())
            if self._last_details is not None:
                payload["details"] = self._last_details
            self.core.socketio.emit("show_resolution", payload, to=sid)

        elif self.state == "SCORING":
            if self._scoring_substate == "SHOW_POINTS":
                payload = {
                    "round": self.current_round,
                    "player_answers": self.answers,
                    "gained": self._last_gained or {},
                    "players_ranked": self._players_ranked_before or self.players_ranked(),
                    "phase": "show_points",
                    "apply_update": False,
                }
                payload.update(self._correct_payload())
                if self._last_details is not None:
                    payload["details"] = self._last_details
                self.core.socketio.emit("show_scoring", payload, to=sid)
            else:
                self.core.socketio.emit(
                    "apply_scoring_update",
                    {
                        "round": self.current_round,
                        "players_ranked": self._players_ranked_after or self.players_ranked(),
                        "phase": "apply_update",
                        "apply_update": True,
                    },
                    to=sid,
                )

    # -------------------------
    # public event handler
    # -------------------------

    def handle_event(self, player_id: str, action: str, payload: dict):
        payload = payload or {}

        if action == "request_pause":
            self._sofortpause_requested = True

            if self.state == "IDLE":
                self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
            return

        if action == "resume_pause":
            if self.state == "PAUSE":
                self._resume_from_pause()
            return

        if action == "video_finished":
            if self.state == "IDLE":
                if self._sofortpause_requested:
                    self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
                    return
                self.play_next_video()
            elif self.state == "QUESTION_VIDEO":
                self.start_question_intro()
            return

        if action == "submit_answer":
            if self.state != "QUESTION_OPEN":
                return
            if not player_id or player_id in self.answers:
                return

            try:
                normalized = self.answer_type.normalize(payload)
            except TypeError:
                normalized = self.answer_type.normalize(payload, num_options=0)

            if normalized is None:
                return

            self.answers[player_id] = normalized
            self.answer_times[player_id] = datetime.now(timezone.utc)

            self.core.socketio.emit("player_logged_in", {"player_id": player_id}, room="tv_room")
            self.core.socketio.emit("player_logged_in", {"player_id": player_id}, room="controller_room")

            if len(self.answers) == len(self.core.players):
                self.close_answers_and_resolve(reason="all_answered")

    # -------------------------
    # flow
    # -------------------------

    def play_next_video(self):
        self.state = "QUESTION_VIDEO"
        payload = {"round": self.current_round + 1}
        self.core.socketio.emit("play_round_video", payload, room="tv_room")
        self.core.socketio.emit("play_round_video", payload, room="controller_room")

    def start_question_intro(self):
        self.state = "QUESTION_INTRO"

        self._scoring_substate = None
        self._last_gained = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False
        self._last_details = None
        self._resolution_scoring_prepared = False

        self._last_open_answers_started_at = None
        self._last_open_answers_duration = None
        self._last_open_answers_started_at_iso = None

        self._correct_unveiled = False

        self.current_round += 1
        self.answers = {}
        self.answer_times = {}

        for p in self.core.players.values():
            p["answered"] = False

        self._round_token += 1
        token = self._round_token

        q = self.question_source.next_question()
        if not q:
            return

        self.active_question = q

        now = datetime.now(timezone.utc)
        self._question_shown_at = now
        self._question_shown_at_iso = self._iso_utc(now)

        unveil_at = now + timedelta(seconds=float(self.timing.intro_delay_seconds))
        self._answers_unveil_at = unveil_at
        self._answers_unveil_at_iso = self._iso_utc(unveil_at)

        self.core.socketio.emit(
            "show_question",
            self._question_payload(),
        )

        self.core.start_task(self._open_answers_after_delay, token)

    def _open_answers_after_delay(self, token: int):
        self.core.sleep(float(self.timing.intro_delay_seconds))
        if token == self._round_token and self.state == "QUESTION_INTRO":
            self.open_answers(token)

    def open_answers(self, token: int):
        self.state = "QUESTION_OPEN"

        self._open_answers_started_at = datetime.now(timezone.utc)
        self._open_answers_duration = float(self.timing.answer_duration_seconds)
        self._open_answers_started_at_iso = self._iso_utc(self._open_answers_started_at)

        self._last_open_answers_started_at = self._open_answers_started_at
        self._last_open_answers_duration = self._open_answers_duration
        self._last_open_answers_started_at_iso = self._open_answers_started_at_iso

        self.core.socketio.emit(
            "open_answers",
            {
                "duration": float(self.timing.answer_duration_seconds),
                "round": self.current_round,
                "started_at": self._open_answers_started_at_iso,
                "total_duration": float(self.timing.answer_duration_seconds),
            },
        )

        self.core.start_task(self._answer_timer_task, token, float(self.timing.answer_duration_seconds))

    def _answer_timer_task(self, token: int, seconds: float):
        self.core.sleep(float(seconds))
        if token == self._round_token and self.state == "QUESTION_OPEN":
            self.close_answers_and_resolve(reason="timer")

    def close_answers_and_resolve(self, reason: str = ""):
        self._last_open_answers_started_at = self._open_answers_started_at
        self._last_open_answers_duration = self._open_answers_duration
        self._last_open_answers_started_at_iso = self._open_answers_started_at_iso

        self._open_answers_started_at = None
        self._open_answers_duration = None
        self._open_answers_started_at_iso = None

        self._round_token += 1
        token = self._round_token

        self.core.socketio.emit(
            "close_answers",
            {"round": self.current_round, "reason": reason},
        )

        self.state = "REVEAL_ANSWERS"

        self.core.start_task(
            self._reveal_answers_with_optional_delay,
            token,
            reason,
        )

    def _reveal_answers_with_optional_delay(self, token: int, reason: str):
        if str(reason or "").lower() == "all_answered":
            self.core.sleep(0.0)

        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return

        self.core.socketio.emit(
            "reveal_player_answers",
            {"player_answers": self.answers},
        )

        self.core.start_task(
            self._unveil_correct_then_resolution,
            token,
        )

    def _unveil_correct_then_resolution(self, token: int):
        total = float(self.timing.reveal_answers_seconds or 0)
        first = max(0.0, total * 0.5)
        second = max(0.0, total - first)

        if first > 0:
            self.core.sleep(first)
        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return

        self._correct_unveiled = True
        payload = {}
        payload.update(self._correct_payload())
        self.core.socketio.emit("unveil_correct", payload)

        if second > 0:
            self.core.sleep(second)
        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return

        self.start_resolution(token)

    def start_resolution(self, token: int):
        self.state = "RESOLUTION"

        # WICHTIGER Unterschied zu FreetextStandardFlow:
        # details/gained jetzt schon vorberechnen, damit show_resolution accepted enthält.
        self._compute_scoring_preview()

        payload = {
            "player_answers": self.answers,
        }
        payload.update(self._correct_payload())
        if self._last_details is not None:
            payload["details"] = self._last_details

        self.core.socketio.emit("show_resolution", payload)

        self.core.start_task(self._scoring_after_resolution, token)

    def _scoring_after_resolution(self, token: int):
        self.core.sleep(float(self.timing.resolution_seconds))
        if token == self._round_token and self.state == "RESOLUTION":
            self.start_scoring(token)

    # -------------------------
    # scoring
    # -------------------------

    def start_scoring(self, token: int):
        self._scoring_substate = None
        self._score_updated_sent = False

        # Falls aus irgendeinem Grund noch nichts vorbereitet wurde: jetzt nachholen
        if not self._resolution_scoring_prepared:
            self._compute_scoring_preview()

        gained = dict(self._last_gained or {})
        details = self._last_details

        any_points = any(v != 0 for v in gained.values())

        # Punkte erst JETZT wirklich anwenden
        for pid, delta in gained.items():
            if delta:
                self.core.players[pid]["score"] = int(self.core.players[pid].get("score", 0) or 0) + int(delta)

        self._players_ranked_after = self.players_ranked()

        if not any_points:
            self.state = "NO_POINTS_HOLD"
            self.core.start_task(
                self._next_round_after_scoring,
                token,
                float(getattr(self.timing, "no_points_hold_seconds", 1.0)),
            )
            return

        self.state = "SCORING"
        self._scoring_substate = "SHOW_POINTS"

        payload = {
            "round": self.current_round,
            "player_answers": self.answers,
            "gained": gained,
            "players_ranked": self._players_ranked_before or self.players_ranked(),
            "phase": "show_points",
            "apply_update": False,
        }
        payload.update(self._correct_payload())
        if details is not None:
            payload["details"] = details

        self.core.socketio.emit("show_scoring", payload)

        self.core.start_task(self._apply_scoring_after_delay, token, float(self.timing.scoring_show_points_seconds))

    def _emit_apply_scoring_update(self):
        if self._score_updated_sent:
            return
        self._score_updated_sent = True

        self.core.socketio.emit(
            "apply_scoring_update",
            {
                "round": self.current_round,
                "players_ranked": self._players_ranked_after or self.players_ranked(),
                "phase": "apply_update",
                "apply_update": True,
            },
        )

    def _apply_scoring_after_delay(self, token: int, delay_seconds: float):
        self.core.sleep(float(delay_seconds))
        if token != self._round_token or self.state != "SCORING" or self._scoring_substate != "SHOW_POINTS":
            return

        self._scoring_substate = "APPLY_UPDATE"
        self._emit_apply_scoring_update()

        self.core.start_task(self._next_round_after_scoring, token, float(self.timing.scoring_hold_after_update_seconds))

    def _next_round_after_scoring(self, token: int, delay_seconds: float):
        self.core.sleep(float(delay_seconds))
        if token != self._round_token or self.state not in ("SCORING", "NO_POINTS_HOLD"):
            return

        self._scoring_substate = None
        self._last_gained = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False
        self._last_details = None
        self._resolution_scoring_prepared = False

        self._last_open_answers_started_at = None
        self._last_open_answers_duration = None
        self._last_open_answers_started_at_iso = None

        self._correct_unveiled = False

        if self.current_round < self.max_rounds:
            if self._sofortpause_requested:
                self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
                return
            self.play_next_video()
        else:
            self.end_game()

    # -------------------------
    # end
    # -------------------------

    def end_game(self):
        if callable(self.core.on_game_finished):
            self.core.on_game_finished()
            return

        self.core.socketio.emit("switch_phase", {}, room="tv_room")
        self.core.socketio.emit("switch_phase", {}, room="controller_room")