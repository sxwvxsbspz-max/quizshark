# --- FILE: ./engine/engine_core.py ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Callable

from engine.ranking import get_players_ranked


@dataclass
class EngineCore:
    """
    Gemeinsamer, flow-agnostischer Kern:
      - socketio + emit helpers
      - players + ranking helper
      - on_game_finished callback

    WICHTIG:
    - KEINE Flow-Logik hier (keine States, keine Timer-Abläufe)
    - Flow kümmert sich um State/Timing/Sequencing
    """

    socketio: any
    players: Dict[str, dict]
    on_game_finished: Optional[Callable[[], None]] = None

    def players_ranked(self):
        return get_players_ranked(self.players)

    # ---- emit helpers ----
    def emit_tv(self, event: str, payload: dict):
        self.socketio.emit(event, payload, room="tv_room")

    def emit_controller(self, event: str, payload: dict):
        self.socketio.emit(event, payload, room="controller_room")

    def emit_all(self, event: str, payload: dict):
        # bisheriges Verhalten: ohne room -> broadcast
        self.socketio.emit(event, payload)

    # ---- scheduling helpers ----
    def start_task(self, fn, *args, **kwargs):
        return self.socketio.start_background_task(fn, *args, **kwargs)

    def sleep(self, seconds: float):
        return self.socketio.sleep(float(seconds))