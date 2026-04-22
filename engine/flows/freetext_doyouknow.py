from __future__ import annotations

from engine.flows.freetext_freeknowledge import FreetextFreeKnowledgeFlow
from engine.scoring.doyouknow_scoring import KiTimeoutAbort


class FreetextDoYouKnowFlow(FreetextFreeKnowledgeFlow):
    """
    Wie FreetextFreeKnowledgeFlow, aber:
    - Kein unveil_correct (kein einzelnes "correct"-Feld)
    - show_resolution enthält examples aus KI-Bewertung
    - Bei KiTimeoutAbort: ki_timeout an TV/Controller, Modul endet sofort
    """

    # -------------------------
    # override: skip unveil_correct, go straight to resolution
    # -------------------------

    def _unveil_correct_then_resolution(self, token: int):
        total = float(self.timing.reveal_answers_seconds or 0)
        if total > 0:
            self.core.sleep(total)
        if token != self._round_token or self.state != "REVEAL_ANSWERS":
            return
        self.start_resolution(token)

    # -------------------------
    # override: catch KiTimeoutAbort
    # -------------------------

    def start_resolution(self, token: int):
        self.state = "RESOLUTION"

        try:
            self._compute_scoring_preview()
        except KiTimeoutAbort:
            self._abort_ki_timeout()
            return

        examples = []
        if self._last_details:
            examples = self._last_details.get("_examples", [])

        payload = {
            "player_answers": self.answers,
            "examples": examples,
        }
        payload.update(self._correct_payload())
        if self._last_details is not None:
            payload["details"] = self._last_details

        self.core.socketio.emit("show_resolution", payload)
        self.core.start_task(self._scoring_after_resolution, token)

    # -------------------------
    # override: include examples on reconnect
    # -------------------------

    def sync_controller_state(self, sid: str):
        if self.state in ("RESOLUTION", "NO_POINTS_HOLD"):
            examples = []
            if self._last_details:
                examples = self._last_details.get("_examples", [])
            payload = {
                "player_answers": self.answers,
                "examples": examples,
            }
            payload.update(self._correct_payload())
            if self._last_details is not None:
                payload["details"] = self._last_details
            self.core.socketio.emit("show_resolution", payload, to=sid)
            return

        super().sync_controller_state(sid)

    # -------------------------
    # abort on KI timeout
    # -------------------------

    def _abort_ki_timeout(self):
        msg = "Unser KI lässt uns gerade im Stich – ab zum nächsten Spiel!"
        payload = {"message": msg}
        self.core.socketio.emit("ki_timeout", payload, room="tv_room")
        self.core.socketio.emit("ki_timeout", payload, room="controller_room")

        if callable(self.core.on_game_finished):
            self.core.on_game_finished()
        else:
            self.core.socketio.emit("switch_phase", {}, room="tv_room")
            self.core.socketio.emit("switch_phase", {}, room="controller_room")
