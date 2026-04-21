# --- FILE: ./engine/scoring/wagered.py ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class WageredScoring:
    """
    Wager-Scoring:
      - richtige Antwort  => +wager
      - falsche/keine     => -wager
      - Score darf NIE unter 0 fallen (negativer Delta wird begrenzt)

    Erwartetes Answer-Format (Standard MC):
      answers[player_id] = int (choice index)
      oder answers[player_id] = {"value": int, ...}
    """
    default_wager: int = 25

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

    def _extract_wager(self, raw_wager: Any) -> int:
        try:
            w = int(raw_wager)
            return w if w > 0 else int(self.default_wager)
        except Exception:
            return int(self.default_wager)

    def compute_gained(
        self,
        *,
        players: Dict[str, dict],
        answers: Dict[str, Any],
        question: dict,
        timing: Any = None,
        wagers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        correct_idx = int(question.get("correct_index"))
        gained: Dict[str, int] = {}

        players = players or {}
        answers = answers or {}
        wagers = wagers or {}

        for pid, p in players.items():
            choice = self._extract_choice(answers.get(pid))
            wager = self._extract_wager(wagers.get(pid, self.default_wager))

            is_correct = (choice is not None) and (int(choice) == correct_idx)
            delta = wager if is_correct else -wager

            # Clamp: niemand darf unter 0 fallen
            current_score = int((p or {}).get("score", 0) or 0)
            if delta < 0:
                delta = max(delta, -current_score)

            gained[pid] = int(delta)

        return gained
