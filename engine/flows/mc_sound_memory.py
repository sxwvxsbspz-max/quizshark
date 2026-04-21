# --- FILE: ./engine/flows/mc_sound_memory.py ---
# SoundMemory-Flow: basiert auf mc_memory, aber MEMO ist FRONTEND-getrieben:
# - Backend zeigt Memo-Screen (Bild + Song)
# - TV spielt Song ab
# - Wenn Song endet, sendet TV: module_event { action: "memo_finished" }
# - Backend geht erst dann weiter (hide_memo -> play_next_video)
# - Not-Aus: nach 4 Minuten automatisch weiter

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any

from engine.engine_core import EngineCore
from engine.answers.answer_base import AnswerTypeBase
from engine.scoring.scoring_base import ScoringBase


# =========================================================
# Timing
# =========================================================

@dataclass
class MemoryQuizTiming:
    # wie Standard
    intro_delay_seconds: float = 3
    answer_duration_seconds: float = 15
    reveal_answers_seconds: float = 3
    resolution_seconds: float = 2
    scoring_show_points_seconds: float = 2
    scoring_hold_after_update_seconds: float = 2
    no_points_hold_seconds: float = 5.0

    # MEMO ist frontend-getrieben; total_duration dient als Anzeige/Not-Aus-Referenz
    memo_duration_seconds: float = 0.0

    # NEU: Not-Aus nach 4 Minuten (240s)
    memo_timeout_seconds: float = 240.0


# =========================================================
# Flow
# =========================================================

class MCSoundMemoryFlow:
    """
    MC-Flow mit zusätzlichem MEMO-Screen:
      INTRO_VIDEO -> MEMO (einmal, frontend-getrieben) -> QUESTION_VIDEO -> QUESTION_INTRO -> QUESTION_OPEN -> REVEAL -> RESOLUTION -> SCORING -> ...

    Wichtig:
    - Memo läuft genau 1x, wie das Intro.
    - Memo-Ende ist FRONTEND-getrieben über action "memo_finished".
    - Not-Aus: nach memo_timeout_seconds geht es automatisch weiter.
    - Pro Frage gibt es ein frageX.mp4 (QUESTION_VIDEO).
    - max_rounds bedeutet hier: Anzahl Fragen in dieser Runde (questions per image).
      (Das "Image" bleibt während der ganzen Runde gleich; das liefert der QuestionSource.)

    Der QuestionSource muss pro Frage mindestens liefern:
      {
        "text": str,
        "options": list[str],
        "correct_index": int,
        "audio": Optional[str],   # frage-audio (kann leer sein)
        "image": Optional[str],   # rundenbild (kann leer sein)
        # optional (falls du trennen willst):
        "memo_audio": Optional[str],  # runden-audio fürs Memo (Song)
        "memo_image": Optional[str],  # rundenbild fürs Memo
      }

    Dummy-Fallback:
      - /soundmemory/media/memoryimagedummy.png
      - /soundmemory/media/memoryimagedummy.mp3
    """

    DUMMY_IMAGE = "/soundmemory/media/memoryimagedummy.png"
    DUMMY_AUDIO = "/soundmemory/media/memoryimagedummy.mp3"

    def __init__(
        self,
        core: EngineCore,
        *,
        max_rounds: int = 1,
        timing: Optional[MemoryQuizTiming] = None,
        scoring: Optional[ScoringBase] = None,
        answer_type: Optional[AnswerTypeBase] = None,
        question_source=None,
    ):
        self.core = core

        self.max_rounds = int(max_rounds or 1)
        self.timing = timing or MemoryQuizTiming()

        # Plug-ins (MUSS gesetzt sein)
        self.scoring: ScoringBase = scoring
        self.answer_type: AnswerTypeBase = answer_type

        self.question_source = question_source

        self.current_round = 0
        self.state = "IDLE"

        self.active_question: Optional[dict] = None
        self.answers: Dict[str, Any] = {}

        # Antwort-Zeitstempel pro Spieler (UTC datetime)
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

        # Timing (absolut)
        self._question_shown_at: Optional[datetime] = None
        self._question_shown_at_iso: Optional[str] = None
        self._answers_unveil_at: Optional[datetime] = None
        self._answers_unveil_at_iso: Optional[str] = None

        # Memo Timing (absolut)
        self._memo_started_at: Optional[datetime] = None
        self._memo_started_at_iso: Optional[str] = None
        self._memo_duration: Optional[float] = None

        # Memo Assets (für Reconnect)
        self._memo_image: str = self.DUMMY_IMAGE
        self._memo_audio: str = self.DUMMY_AUDIO

        # Merker: Memo nur einmal wie Intro
        self._memo_shown_once: bool = False
        self._memo_round: int = 1

        # SCORING substates for reconnect
        self._scoring_substate: Optional[str] = None
        self._last_gained: Optional[Dict[str, int]] = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False

        # Merker, ob unveil_correct bereits gesendet wurde (für Reconnect in REVEAL_ANSWERS)
        self._correct_unveiled: bool = False

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

    def _norm_media(self, value: Optional[str], *, kind: str) -> str:
        """
        Normalisiert Media-Felder:
        - akzeptiert None/"" => Dummy
        - akzeptiert absolute URLs/Paths
        - akzeptiert "filename.ext" => wird NICHT automatisch geprefixt
          (damit kannst du später selbst entscheiden, ob du filenames oder paths speicherst)
        """
        v = (value or "").strip()
        if not v:
            return self.DUMMY_IMAGE if kind == "image" else self.DUMMY_AUDIO
        return v

    # -------------------------
    # Pause helpers
    # -------------------------

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

        if target == "START_ROUND":
            self.start_round()
            return

        # fallback
        self.play_next_video()

    # -------------------------
    # reconnect sync (controller)
    # -------------------------

    def sync_controller_state(self, sid: str):
        # Pause priorisieren
        if self.state == "PAUSE":
            self._emit_show_pause(to=sid)
            return

        # Kein active_question: ggf. im Video/Idle
        if not self.active_question:
            if self.state == "QUESTION_VIDEO":
                self.core.socketio.emit("play_round_video", {"round": self.current_round + 1}, to=sid)
            return

        # Memo-Screen resync
        if self.state == "MEMO":
            remaining = float(getattr(self.timing, "memo_timeout_seconds", 240.0) or 240.0)
            total = float(getattr(self.timing, "memo_timeout_seconds", 240.0) or 240.0)
            started_iso = self._memo_started_at_iso

            if self._memo_started_at and self._memo_duration:
                elapsed = (datetime.now(timezone.utc) - self._memo_started_at).total_seconds()
                remaining = max(0.0, float(self._memo_duration) - float(elapsed))
                total = float(self._memo_duration)

            self.core.socketio.emit(
                "show_memo",
                {
                    "round": int(self._memo_round),
                    "image": self._memo_image,
                    "audio": self._memo_audio,
                    "started_at": started_iso,
                    "total_duration": float(total),
                    "remaining": float(remaining),
                },
                to=sid,
            )
            return

        # Standard: Question anzeigen (wie mc_standard)
        self.core.socketio.emit(
            "show_question",
            {
                "text": self.active_question["text"],
                "options": self.active_question["options"],
                "round": self.current_round,
                "players": self.core.players,
                "players_ranked": self.players_ranked(),
                "audio": self.active_question.get("audio"),
                "image": self.active_question.get("image"),

                "question_shown_at": self._question_shown_at_iso,
                "answers_unveil_at": self._answers_unveil_at_iso,
            },
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
                self.core.socketio.emit(
                    "unveil_correct",
                    {"correct_index": self.active_question["correct_index"]},
                    to=sid,
                )

        elif self.state in ("RESOLUTION", "NO_POINTS_HOLD"):
            self.core.socketio.emit(
                "show_resolution",
                {
                    "correct_index": self.active_question["correct_index"],
                    "player_answers": self.answers,
                },
                to=sid,
            )

        elif self.state == "SCORING":
            if self._scoring_substate == "SHOW_POINTS":
                self.core.socketio.emit(
                    "show_scoring",
                    {
                        "round": self.current_round,
                        "correct_index": self.active_question["correct_index"],
                        "player_answers": self.answers,
                        "gained": self._last_gained or {},
                        "players_ranked": self._players_ranked_before or self.players_ranked(),
                        "phase": "show_points",
                        "apply_update": False,
                    },
                    to=sid,
                )
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

        # Sofortpause toggle
        if action == "request_pause":
            self._sofortpause_requested = True
            if self.state == "IDLE":
                self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
            return

        if action == "resume_pause":
            if self.state == "PAUSE":
                self._resume_from_pause()
            return

        # NEU: Memo-Ende (FRONTEND-getrieben)
        if action == "memo_finished":
            if self.state == "MEMO":
                self._round_token += 1
                token = self._round_token
                self.core.socketio.emit("hide_memo", {"round": int(self._memo_round)})
                self.play_next_video()
            return

        if action == "video_finished":
            if self.state == "IDLE":
                if self._sofortpause_requested:
                    self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
                    return

                # Memo genau 1x nach dem Intro-Video
                if not self._memo_shown_once:
                    self.start_memo_once()
                    return

                self.play_next_video()

            elif self.state == "QUESTION_VIDEO":
                self.start_round()
            return

        if action == "submit_answer":
            if self.state != "QUESTION_OPEN":
                return
            if not player_id or player_id in self.answers:
                return

            normalized = self.answer_type.normalize(
                payload,
                num_options=len(self.active_question.get("options", [])),
            )
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

    def start_memo_once(self):
        """
        Memo wie Intro: genau 1x am Anfang.
        - zieht die erste Frage (active_question), damit wir Memo-Assets haben
        - zeigt Memo
        - wartet auf FRONTEND "memo_finished"
        - Not-Aus: nach memo_timeout_seconds automatisch weiter
        """
        self._memo_shown_once = True
        self.state = "MEMO"

        # Reset scoring / snapshots (sauberer Start)
        self._scoring_substate = None
        self._last_gained = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False

        self._last_open_answers_started_at = None
        self._last_open_answers_duration = None
        self._last_open_answers_started_at_iso = None

        self._correct_unveiled = False

        self.answers = {}
        self.answer_times = {}

        for p in self.core.players.values():
            p["answered"] = False

        self._round_token += 1
        token = self._round_token

        # Erste Frage schon jetzt holen (damit Memo Bild/Audio hat)
        q = self.question_source.next_question()
        if not q:
            return

        self.active_question = q
        self._memo_round = int(self.current_round + 1)

        # Memo assets bestimmen (Keys tolerant)
        memo_image = (
            q.get("memo_image")
            or q.get("image")
            or q.get("round_image")
            or q.get("image_path")
        )
        memo_audio = (
            q.get("memo_audio")
            or q.get("bgm")
            or q.get("image_audio")
            or q.get("round_audio")
        )

        self._memo_image = self._norm_media(memo_image, kind="image")
        self._memo_audio = self._norm_media(memo_audio, kind="audio")

        now = datetime.now(timezone.utc)
        self._memo_started_at = now
        self._memo_started_at_iso = self._iso_utc(now)

        # Memo-Dauer hier als Not-Aus/Anzeige-Referenz
        self._memo_duration = float(getattr(self.timing, "memo_timeout_seconds", 240.0) or 240.0)

        # Memo anzeigen (TV + Controller)
        self.core.socketio.emit(
            "show_memo",
            {
                "round": int(self._memo_round),
                "image": self._memo_image,
                "audio": self._memo_audio,
                "started_at": self._memo_started_at_iso,
                "total_duration": float(self._memo_duration),
                "remaining": float(self._memo_duration),
            },
        )

        # Not-Aus Task (4 Minuten)
        self.core.start_task(self._memo_timeout_task, token)

    def _memo_timeout_task(self, token: int):
        seconds = float(getattr(self.timing, "memo_timeout_seconds", 240.0) or 240.0)
        if seconds > 0:
            self.core.sleep(seconds)

        if token != self._round_token or self.state != "MEMO":
            return

        self.core.socketio.emit("hide_memo", {"round": int(self._memo_round)})
        self.play_next_video()

    def play_next_video(self):
        self.state = "QUESTION_VIDEO"
        payload = {"round": self.current_round + 1}
        self.core.socketio.emit("play_round_video", payload, room="tv_room")
        self.core.socketio.emit("play_round_video", payload, room="controller_room")

    def start_round(self):
        """
        Zeigt die Frage (OHNE Memo, weil Memo nur 1x wie Intro kommt).
        - wenn active_question schon gesetzt ist (vom Memo), wird diese genutzt
        - sonst: next_question()
        - show_question + intro_delay -> open_answers
        """
        # Reset scoring / snapshots
        self.state = "QUESTION_INTRO"

        self._scoring_substate = None
        self._last_gained = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False

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

        # Frage holen (oder die vom Memo verwenden)
        q = self.active_question
        if not q:
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
            {
                "text": q["text"],
                "options": q["options"],
                "round": self.current_round,
                "players": self.core.players,
                "players_ranked": self.players_ranked(),
                "audio": q.get("audio"),
                "image": q.get("image"),

                "question_shown_at": self._question_shown_at_iso,
                "answers_unveil_at": self._answers_unveil_at_iso,
            },
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

        self.core.socketio.emit("close_answers", {"round": self.current_round, "reason": reason})

        self.state = "REVEAL_ANSWERS"

        self.core.start_task(self._reveal_answers_with_optional_delay, token, reason)

    def _reveal_answers_with_optional_delay(self, token: int, reason: str):
        if str(reason or "").lower() == "all_answered":
            self.core.sleep(0.0)

        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return

        self.core.socketio.emit("reveal_player_answers", {"player_answers": self.answers})

        self.core.start_task(self._unveil_correct_then_resolution, token)

    def _unveil_correct_then_resolution(self, token: int):
        total = float(self.timing.reveal_answers_seconds or 0)
        first = max(0.0, total * 0.5)
        second = max(0.0, total - first)

        if first > 0:
            self.core.sleep(first)
        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return

        self._correct_unveiled = True
        self.core.socketio.emit("unveil_correct", {"correct_index": self.active_question["correct_index"]})

        if second > 0:
            self.core.sleep(second)
        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return

        self.start_resolution(token)

    def start_resolution(self, token: int):
        self.state = "RESOLUTION"
        self.core.socketio.emit(
            "show_resolution",
            {
                "correct_index": self.active_question["correct_index"],
                "player_answers": self.answers,
            },
        )

        self.core.start_task(self._scoring_after_resolution, token)

    def _scoring_after_resolution(self, token: int):
        self.core.sleep(float(self.timing.resolution_seconds))
        if token == self._round_token and self.state == "RESOLUTION":
            self.start_scoring(token)

    # -------------------------
    # scoring (delegiert)
    # -------------------------

    def start_scoring(self, token: int):
        self._scoring_substate = None
        self._score_updated_sent = False

        self._players_ranked_before = self.players_ranked()

        gained = self.scoring.compute_gained(
            players=self.core.players,
            answers=self.answers,
            question=self.active_question,
            timing={
                "open_started_at": self._last_open_answers_started_at,
                "open_duration": self._last_open_answers_duration,
                "answer_times": self.answer_times,
            },
        )

        self._last_gained = gained
        any_points = any(v != 0 for v in gained.values())

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

        self.core.socketio.emit(
            "show_scoring",
            {
                "round": self.current_round,
                "correct_index": self.active_question["correct_index"],
                "player_answers": self.answers,
                "gained": gained,
                "players_ranked": self._players_ranked_before,
                "phase": "show_points",
                "apply_update": False,
            },
        )

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

        self._last_open_answers_started_at = None
        self._last_open_answers_duration = None
        self._last_open_answers_started_at_iso = None

        self._correct_unveiled = False

        # WICHTIG: active_question aufräumen, damit nächste Runde frisch zieht
        self.active_question = None

        # Runde weiter oder Ende
        if self.current_round < self.max_rounds:
            # Safe-Point nach Scoring, bevor nächstes Video startet
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
