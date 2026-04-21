# --- FILE: ./engine/flows/mc_haveiever.py ---
# mc_standard 1:1 ERHALTEN + vorgelagerter POLL Block (Have I ever)
# NICHTS aus mc_standard entfernt oder vereinfacht

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List, Tuple

from engine.engine_core import EngineCore
from engine.answers.answer_base import AnswerTypeBase
from engine.scoring.scoring_base import ScoringBase


@dataclass
class HaveIEverTiming:
    # NEU: vorgelagerter Block
    poll_duration_seconds: float = 12.0
    poll_close_hold_seconds: float = 2.0

    # IDENTISCH zu mc_standard
    intro_delay_seconds: float = 3
    answer_duration_seconds: float = 15
    reveal_answers_seconds: float = 3
    resolution_seconds: float = 2
    scoring_show_points_seconds: float = 2
    scoring_hold_after_update_seconds: float = 2
    no_points_hold_seconds: float = 5.0


class MCHaveIEverFlow:
    """
    Flow:
      QUESTION_VIDEO
        -> POLL_OPEN (Ja/Nein, anonym)
        -> (danach 1:1 mc_standard)

    Wichtig:
      - KEIN Poll-Reveal (keine Zuordnung Ja/Nein zu Spielern)
      - Nicht-Abstimmer zählen NICHT in votes_cast
      - MC-Frage zeigt votes_cast (Anzahl abgegebener Votes)
      - 2 Audios: pre_audio (für Poll) und audio (für MC)
    """

    VOTE_NO = 0
    VOTE_YES = 1

    def __init__(
        self,
        core: EngineCore,
        *,
        max_rounds: int = 1,
        timing: Optional[HaveIEverTiming] = None,
        scoring: Optional[ScoringBase] = None,
        answer_type: Optional[AnswerTypeBase] = None,
        question_source=None,
    ):
        self.core = core

        self.max_rounds = int(max_rounds or 1)
        self.timing = timing or HaveIEverTiming()

        # Plug-ins (MUSS gesetzt sein)
        self.scoring: ScoringBase = scoring
        self.answer_type: AnswerTypeBase = answer_type
        self.question_source = question_source

        self.current_round = 0
        self.state = "IDLE"

        self.active_question: Optional[dict] = None

        # -------------------------
        # ANSWERS (mc_standard)
        # -------------------------

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

        # -------------------------
        # NEU: POLL
        # -------------------------

        # anonym: wir speichern intern Ja/Nein pro player_id,
        # aber senden NIE Ja/Nein pro player_id ans Frontend.
        self.poll_votes: Dict[str, int] = {}

        self._poll_started_at: Optional[datetime] = None
        self._poll_started_at_iso: Optional[str] = None

        # Snapshot für MC-Frage (damit reconnect / frontend Anzeige stabil ist)
        self._poll_votes_cast: int = 0
        self._poll_yes_count: int = 0

        # -------------------------
        # SCORING (mc_standard)
        # -------------------------

        self._scoring_substate: Optional[str] = None
        self._last_gained: Optional[Dict[str, int]] = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False

        # Correct unveil marker
        self._correct_unveiled: bool = False

        # Pause
        self._sofortpause_requested: bool = False
        self._pause_resume_target: Optional[str] = None

    # --------------------------------------------------
    # helpers (mc_standard)
    # --------------------------------------------------

    def players_ranked(self):
        return self.core.players_ranked()

    def _iso_utc(self, dt: Optional[datetime]) -> Optional[str]:
        if not isinstance(dt, datetime):
            return None
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # --------------------------------------------------
    # NEU: Pause helpers (wie mc_standard)
    # --------------------------------------------------

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
        self._pause_resume_target = str(resume_target or "PLAY_NEXT_VIDEO")
        self.state = "PAUSE"
        self._emit_show_pause()

    def _resume_from_pause(self):
        self._emit_hide_pause()
        target = self._pause_resume_target or "PLAY_NEXT_VIDEO"
        self._pause_resume_target = None

        # Default: weiter wie "nächster Schritt"
        if target == "PLAY_NEXT_VIDEO":
            self.play_next_video()
            return

        if target == "START_QUESTION_INTRO":
            self.start_question_intro()
            return

        # Fallback
        self.play_next_video()

    # --------------------------------------------------
    # NEU: MC-Optionen (Zahlen) für "Wie viele...?"
    # --------------------------------------------------

    def _weighted_pick(self, pool: List[int], center: int) -> Optional[int]:
        if not pool:
            return None
        # Gewichtung: je näher an center, desto wahrscheinlicher
        weights = []
        for v in pool:
            d = abs(int(v) - int(center))
            w = 1.0 / (1.0 + float(d))
            weights.append(w)
        return random.choices(pool, weights=weights, k=1)[0]

    def _build_number_options(self, correct_yes: int, votes_cast: int) -> Tuple[List[int], int]:
        """
        Liefert: (options_ints, correct_index)
        Regeln:
          - wenn votes_cast < 3 -> immer [0,1,2,3]
          - sonst: alle Optionen innerhalb [0..votes_cast], jede Zahl nur 1x
          - 4 verschiedene Logiken werden zufällig gewählt
        """
        correct_yes = int(correct_yes)
        votes_cast = int(votes_cast)

        # Edge Case: < 3 Votes => immer 0,1,2,3 (auch wenn 3 "klar falsch" ist)
        if votes_cast < 3:
            opts = [0, 1, 2, 3]
            ci = opts.index(correct_yes) if correct_yes in opts else 0
            return opts, ci

        lo = 0
        hi = votes_cast

        # immer valid
        correct_yes = max(lo, min(hi, correct_yes))

        strategy = random.choice([1, 2, 3, 4])

        chosen = {correct_yes}

        def add_if_valid(x: int):
            x = int(x)
            if lo <= x <= hi and x not in chosen:
                chosen.add(x)

        # ---- Strategy 1: "Near cluster" (nahe am correct)
        if strategy == 1:
            offsets = [-2, -1, 1, 2, -3, 3]
            random.shuffle(offsets)
            for off in offsets:
                if len(chosen) >= 4:
                    break
                add_if_valid(correct_yes + off)

        # ---- Strategy 2: "Anchors" (0 / max / +1 nahe correct)
        elif strategy == 2:
            # extreme nur nehmen, wenn sie nicht komplett absurd weit weg sind
            # (trotzdem immer innerhalb [0..hi])
            add_if_valid(0)
            add_if_valid(hi)

            # dritter distractor: nahe correct, aber nicht gleich
            for off in [1, -1, 2, -2, 3, -3]:
                if len(chosen) >= 4:
                    break
                add_if_valid(correct_yes + off)

        # ---- Strategy 3: "Mirror" (symmetrisch um correct)
        elif strategy == 3:
            max_step = max(1, min(4, hi))
            steps = list(range(1, max_step + 1))
            random.shuffle(steps)
            for d in steps:
                if len(chosen) >= 4:
                    break
                add_if_valid(correct_yes - d)
                if len(chosen) >= 4:
                    break
                add_if_valid(correct_yes + d)

        # ---- Strategy 4: "Biased" (je nachdem ob correct eher hoch/niedrig ist)
        else:
            # wenn correct sehr hoch: distractors eher hoch
            # wenn correct sehr niedrig: distractors eher niedrig
            if correct_yes >= int(hi * 0.7):
                candidates = [hi, hi - 1, hi - 2, correct_yes - 1, correct_yes - 2, correct_yes - 3]
            elif correct_yes <= int(hi * 0.3):
                candidates = [0, 1, 2, correct_yes + 1, correct_yes + 2, correct_yes + 3]
            else:
                candidates = [correct_yes - 2, correct_yes - 1, correct_yes + 1, correct_yes + 2, 0, hi]

            random.shuffle(candidates)
            for c in candidates:
                if len(chosen) >= 4:
                    break
                add_if_valid(c)

        # Fallback-Fill: falls noch nicht voll, random aber gewichtet nahe correct
        if len(chosen) < 4:
            remaining = [v for v in range(lo, hi + 1) if v not in chosen]
            while len(chosen) < 4 and remaining:
                pick = self._weighted_pick(remaining, correct_yes)
                if pick is None:
                    break
                chosen.add(pick)
                remaining = [v for v in remaining if v != pick]

        # final: Liste, dann shuffle
        opts = list(chosen)
        # safety (sollte nie passieren)
        opts = [v for v in opts if lo <= v <= hi]
        opts = list(dict.fromkeys(opts))  # unique preserve order
        # falls durch safety weniger als 4: auffüllen (sollte praktisch nicht passieren)
        if len(opts) < 4:
            for v in range(lo, hi + 1):
                if v not in opts:
                    opts.append(v)
                    if len(opts) >= 4:
                        break
        opts = opts[:4]

        random.shuffle(opts)
        correct_index = opts.index(correct_yes) if correct_yes in opts else 0
        return opts, correct_index

    # --------------------------------------------------
    # reconnect sync (controller) – erweitert, nichts entfernt
    # --------------------------------------------------

    def sync_controller_state(self, sid: str):
        if self.state == "PAUSE":
            self.core.socketio.emit("show_pause", {"mode": "sofortpause"}, to=sid)
            return

        if not self.active_question:
            if self.state == "QUESTION_VIDEO":
                self.core.socketio.emit("play_round_video", {"round": self.current_round + 1}, to=sid)
            return

        if self.state == "POLL_OPEN":
            remaining = float(self.timing.poll_duration_seconds)
            started_iso = self._poll_started_at_iso

            if self._poll_started_at:
                elapsed = (datetime.now(timezone.utc) - self._poll_started_at).total_seconds()
                remaining = max(0.0, float(self.timing.poll_duration_seconds) - elapsed)

            # WICHTIG: KEINE Ja/Nein Werte senden.
            # Optional: wer überhaupt gevotet hat (Status), damit UIs resyncen können.
            voted_players = list(self.poll_votes.keys())

            self.core.socketio.emit(
                "show_poll",
                {
                    "round": self.current_round,
                    "text": self.active_question.get("poll_text") or self.active_question.get("text") or "",
                    "pre_audio": self.active_question.get("pre_audio"),
                    "image": self.active_question.get("image"),
                    "players_ranked": self.players_ranked(),
                    "votes_cast": int(len(self.poll_votes)),
                    "voted_players": voted_players,
                    "started_at": started_iso,
                    "total_duration": float(self.timing.poll_duration_seconds),
                    "remaining": float(remaining),
                },
                to=sid,
            )
            return

        if self.state == "POLL_HOLD":
            # WICHTIG: KEINE Ja/Nein Werte senden.
            voted_players = list(self.poll_votes.keys())

            self.core.socketio.emit(
                "show_poll",
                {
                    "round": self.current_round,
                    "text": self.active_question.get("poll_text") or self.active_question.get("text") or "",
                    "pre_audio": self.active_question.get("pre_audio"),
                    "image": self.active_question.get("image"),
                    "players_ranked": self.players_ranked(),
                    "votes_cast": int(len(self.poll_votes)),
                    "voted_players": voted_players,
                    "started_at": self._poll_started_at_iso,
                    "total_duration": float(self.timing.poll_duration_seconds),
                    "remaining": 0.0,
                },
                to=sid,
            )
            self.core.socketio.emit("close_poll", {"round": self.current_round, "reason": "hold"}, to=sid)
            return

        # -------------------------
        # AB HIER 1:1 mc_standard
        # (zusätzlich: votes_cast mitsenden)
        # -------------------------

        self.core.socketio.emit(
            "show_question",
            {
                "text": self.active_question["text"],
                "options": self.active_question["options"],
                "round": self.current_round,
                "players": self.core.players,
                "players_ranked": self.players_ranked(),
                "audio": self.active_question.get("audio"),
                "pre_audio": self.active_question.get("pre_audio"),
                "image": self.active_question.get("image"),
                "question_shown_at": self._question_shown_at_iso,
                "answers_unveil_at": self._answers_unveil_at_iso,

                # NEU: Anzeige "x Votes abgegeben"
                "votes_cast": int(self.active_question.get("votes_cast") or self._poll_votes_cast or 0),
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

    # --------------------------------------------------
    # public event handler (mc_standard + poll)
    # --------------------------------------------------

    def handle_event(self, player_id: str, action: str, payload: dict):
        payload = payload or {}

        # NEU: Sofortpause toggle (system)
        if action == "request_pause":
            self._sofortpause_requested = True

            # Wenn wir wirklich "vor dem ersten Video" pausieren wollen:
            if self.state == "IDLE":
                self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
            return

        if action == "resume_pause":
            if self.state == "PAUSE":
                self._resume_from_pause()
            return

        if action == "video_finished":
            if self.state == "IDLE":
                # NEU: Safe-Point vor erstem Video
                if self._sofortpause_requested:
                    self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
                    return
                self.play_next_video()
            elif self.state == "QUESTION_VIDEO":
                self.start_poll()
            return

        if action == "submit_poll":
            if self.state != "POLL_OPEN":
                return
            if not player_id or player_id in self.poll_votes:
                return

            raw = payload.get("value", None)
            try:
                v = int(raw)
            except Exception:
                return

            if v not in (self.VOTE_NO, self.VOTE_YES):
                return

            self.poll_votes[player_id] = v

            # anonym: kein Ja/Nein senden!
            votes_cast = int(len(self.poll_votes))

            self.core.socketio.emit(
                "poll_update",
                {"player_id": player_id, "votes_cast": votes_cast},
                room="tv_room",
            )
            self.core.socketio.emit(
                "poll_update",
                {"player_id": player_id, "votes_cast": votes_cast},
                room="controller_room",
            )

            # wenn wirklich alle abgestimmt haben -> Poll sofort schließen + kurze Pause, dann MC starten
            if len(self.poll_votes) == len(self.core.players):
                self.core.socketio.emit("close_poll", {"round": self.current_round, "reason": "all_voted"}, room="tv_room")
                self.core.socketio.emit("close_poll", {"round": self.current_round, "reason": "all_voted"}, room="controller_room")

                self.state = "POLL_HOLD"

                self._round_token += 1
                token = self._round_token

                hold = float(getattr(self.timing, "poll_close_hold_seconds", 0.0) or 0.0)
                if hold <= 0.0:
                    self._close_poll_and_start_mc(reason="all_voted")
                else:
                    self.core.start_task(self._poll_close_hold_task, token, hold, "all_voted")
            return

        # -------------------------
        # mc_standard submit_answer
        # -------------------------

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

    # --------------------------------------------------
    # flow
    # --------------------------------------------------

    def play_next_video(self):
        self.state = "QUESTION_VIDEO"
        payload = {"round": self.current_round + 1}
        self.core.socketio.emit("play_round_video", payload, room="tv_room")
        self.core.socketio.emit("play_round_video", payload, room="controller_room")

    # -------------------------
    # NEU: POLL
    # -------------------------

    def start_poll(self):
        self.state = "POLL_OPEN"

        self._scoring_substate = None
        self._last_gained = None
        self._players_ranked_before = None
        self._players_ranked_after = None
        self._score_updated_sent = False

        self._last_open_answers_started_at = None
        self._last_open_answers_duration = None
        self._last_open_answers_started_at_iso = None

        self._correct_unveiled = False

        # NEW ROUND
        self.current_round += 1
        self.answers = {}
        self.answer_times = {}

        # Poll reset
        self.poll_votes = {}
        self._poll_votes_cast = 0
        self._poll_yes_count = 0
        self._poll_started_at = None
        self._poll_started_at_iso = None

        for p in self.core.players.values():
            p["answered"] = False

        self._round_token += 1
        token = self._round_token

        q = self.question_source.next_question()
        if not q:
            return

        self.active_question = q

        # Poll start time
        self._poll_started_at = datetime.now(timezone.utc)
        self._poll_started_at_iso = self._iso_utc(self._poll_started_at)

        # Poll anzeigen (in beide Rooms)
        self.core.socketio.emit(
            "show_poll",
            {
                "round": self.current_round,
                "text": q.get("poll_text") or q.get("text") or "",
                "pre_audio": q.get("pre_audio"),
                "image": q.get("image"),
                "players_ranked": self.players_ranked(),
                "votes_cast": 0,
                "voted_players": [],
                "started_at": self._poll_started_at_iso,
                "total_duration": float(self.timing.poll_duration_seconds),
            },
            room="tv_room",
        )
        self.core.socketio.emit(
            "show_poll",
            {
                "round": self.current_round,
                "text": q.get("poll_text") or q.get("text") or "",
                "pre_audio": q.get("pre_audio"),
                "image": q.get("image"),
                "players_ranked": self.players_ranked(),
                "votes_cast": 0,
                "voted_players": [],
                "started_at": self._poll_started_at_iso,
                "total_duration": float(self.timing.poll_duration_seconds),
            },
            room="controller_room",
        )

        self.core.start_task(self._poll_timer_task, token, float(self.timing.poll_duration_seconds))

    def _poll_timer_task(self, token: int, seconds: float):
        self.core.sleep(float(seconds))
        if token == self._round_token and self.state == "POLL_OPEN":
            self._close_poll_and_start_mc(reason="timer")

    def _poll_close_hold_task(self, token: int, seconds: float, reason: str):
        self.core.sleep(float(seconds))
        if token == self._round_token and self.state == "POLL_HOLD":
            self._close_poll_and_start_mc(reason=reason)

    def _close_poll_and_start_mc(self, reason: str):
        # Poll schließen (UI stop)
        self.core.socketio.emit("close_poll", {"round": self.current_round, "reason": reason}, room="tv_room")
        self.core.socketio.emit("close_poll", {"round": self.current_round, "reason": reason}, room="controller_room")

        # Snapshot berechnen (Nicht-Abstimmer werden NICHT gezählt)
        votes_cast = int(len(self.poll_votes))
        yes_count = int(sum(1 for v in self.poll_votes.values() if int(v) == self.VOTE_YES))

        self._poll_votes_cast = votes_cast
        self._poll_yes_count = yes_count

        # MC-Optionen generieren (Zahlen)
        opts_int, correct_idx = self._build_number_options(yes_count, votes_cast)

        # MC-Text: bevorzugt mc_text, sonst text
        mc_text = (
            self.active_question.get("mc_text")
            or self.active_question.get("text")
            or ""
        )

        # active_question für mc_standard "fertig machen"
        self.active_question["text"] = mc_text
        self.active_question["options"] = [str(x) for x in opts_int]
        self.active_question["correct_index"] = int(correct_idx)

        # fürs Frontend (Anzeige: "x Votes abgegeben")
        self.active_question["votes_cast"] = int(votes_cast)

        # NEU: Safe-Point nach Poll, bevor MC startet
        if self._sofortpause_requested:
            self._enter_pause(resume_target="START_QUESTION_INTRO")
            return

        # jetzt direkt in mc_standard-Intro wechseln
        self.start_question_intro()

    # -------------------------
    # AB HIER: mc_standard UNVERÄNDERT
    # (zusätzlich: votes_cast im show_question Payload)
    # -------------------------

    def start_question_intro(self):
        self.state = "QUESTION_INTRO"

        self._answers_unveil_at = None
        self._answers_unveil_at_iso = None

        now = datetime.now(timezone.utc)
        self._question_shown_at = now
        self._question_shown_at_iso = self._iso_utc(now)

        unveil_at = now + timedelta(seconds=float(self.timing.intro_delay_seconds))
        self._answers_unveil_at = unveil_at
        self._answers_unveil_at_iso = self._iso_utc(unveil_at)

        self.core.socketio.emit(
            "show_question",
            {
                "text": self.active_question["text"],
                "options": self.active_question["options"],
                "round": self.current_round,
                "players": self.core.players,
                "players_ranked": self.players_ranked(),
                "audio": self.active_question.get("audio"),
                "pre_audio": self.active_question.get("pre_audio"),
                "image": self.active_question.get("image"),
                "question_shown_at": self._question_shown_at_iso,
                "answers_unveil_at": self._answers_unveil_at_iso,

                # NEU: Anzeige "x Votes abgegeben"
                "votes_cast": int(self.active_question.get("votes_cast") or self._poll_votes_cast or 0),
            },
        )

        self.core.start_task(self._open_answers_after_delay, self._round_token)

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

        self.core.start_task(self._reveal_answers_with_optional_delay, token, reason)

    def _reveal_answers_with_optional_delay(self, token: int, reason: str):
        if str(reason or "").lower() == "all_answered":
            self.core.sleep(0.0)

        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return

        self.core.socketio.emit(
            "reveal_player_answers",
            {"player_answers": self.answers},
        )

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
        self.core.socketio.emit(
            "unveil_correct",
            {"correct_index": self.active_question["correct_index"]},
        )

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

        if self.current_round < self.max_rounds:
            # NEU: Safe-Point nach Scoring, bevor nächstes Video startet
            if self._sofortpause_requested:
                self._enter_pause(resume_target="PLAY_NEXT_VIDEO")
                return
            self.play_next_video()
        else:
            self.end_game()

    # --------------------------------------------------
    # end
    # --------------------------------------------------

    def end_game(self):
        if callable(self.core.on_game_finished):
            self.core.on_game_finished()
            return

        self.core.socketio.emit("switch_phase", {}, room="tv_room")
        self.core.socketio.emit("switch_phase", {}, room="controller_room")
