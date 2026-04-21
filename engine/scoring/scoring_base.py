# --- FILE: ./engine/scoring/scoring_base.py ---

from __future__ import annotations

from typing import Any, Dict


class ScoringBase:
    """
    Basis-Interface für alle Scoring-Module.

    Jedes Scoring-Modul MUSS implementieren:
      compute_gained(...)

    Rückgabewert:
      dict[player_id] -> int (gewonnene Punkte, kann auch 0 oder negativ sein)
    """

    def compute_gained(
        self,
        *,
        players: Dict[str, dict],
        answers: Dict[str, Any],
        question: dict,
        timing: Any = None,
    ) -> Dict[str, int]:
        raise NotImplementedError("Scoring module must implement compute_gained()")