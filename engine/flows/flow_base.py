# --- FILE: ./engine/flows/flow_base.py ---

from __future__ import annotations

from typing import Any


class FlowBase:
    """
    Basis-Interface für Flows.

    Ein Flow ist zuständig für:
      - States / Sequencing / Timer
      - Emission der UI-Events
      - Reconnect-Sync (controller/tv)
      - Verarbeitung von module_event Actions

    EngineCore bleibt "dumm" (nur Infrastruktur).
    """

    def sync_controller_state(self, sid: str):
        raise NotImplementedError

    def handle_event(self, player_id: str, action: str, payload: dict):
        raise NotImplementedError

    def players_ranked(self):
        raise NotImplementedError