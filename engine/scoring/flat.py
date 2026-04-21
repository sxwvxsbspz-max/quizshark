# --- FILE: ./engine/scoring/flat.py ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class FlatScoring:
    """
    Flat-Scoring:
      - richtige Antwort => feste Punkte
      - falsche/keine Antwort => 0

    Erwartetes Answer-Format (Standard MC):
      answers[player_id] = int (choice index)
      oder answers[player_id] = {"value": int, ...}  (falls später timestamps ergänzt werden)
    """
    points_per_correct: int = 100

    def _extract_choice(self, raw_answer: Any) -> Optional[int]:
        if raw_answer is None:
            return None
        if isinstance(raw_answer, dict):
            v = raw_answer.get("value", None)
            try:
                return int(v) if v is not None else None
            except Exception:
                return None
        try:
            return int(raw_answer)
        except Exception:
            return None

    def compute_gained(
        self,
        *,
        players: Dict[str, dict],
        answers: Dict[str, Any],
        question: dict,
        timing: Any = None,
    ) -> Dict[str, int]:
        correct_idx = int(question.get("correct_index"))
        gained: Dict[str, int] = {}

        for pid in (players or {}):
            choice = self._extract_choice((answers or {}).get(pid))
            gained[pid] = int(self.points_per_correct) if choice == correct_idx else 0

        return gained