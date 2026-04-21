# --- FILE: ./engine/scoring/time_linear.py ---

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class TimeLinearScoring:
    """
    Zeitbasiertes Scoring (linear):
      - richtige Antwort => Punkte abhängig von Antwortzeit innerhalb der Open-Phase
      - max_points bei sofortiger Antwort, min_points bei Ablauf der Zeit
      - falsche/keine Antwort => 0

    Erwartet:
      - answers[player_id] = int (choice index)  ODER {"value": int, ...}
      - timing["open_started_at"] = datetime (UTC)
      - timing["open_duration"] = float (Sekunden)
      - timing["answer_times"] optional: dict[player_id] -> datetime (UTC)
        (wird bei dir im Flow gesetzt)
    """

    max_points: int = 150
    min_points: int = 50

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

    def _compute_points(self, elapsed: float, duration: float) -> int:
        # clamp
        d = max(0.001, float(duration))
        t = min(max(0.0, float(elapsed)), d)

        # linear: t=0 => max, t=duration => min
        span = int(self.max_points) - int(self.min_points)
        p = float(self.max_points) - (span * (t / d))

        # runden + clamp
        pi = int(round(p))
        return max(int(self.min_points), min(int(self.max_points), pi))

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

        timing = timing or {}
        open_started_at: Optional[datetime] = timing.get("open_started_at")
        open_duration: Optional[float] = timing.get("open_duration")
        answer_times: Dict[str, datetime] = timing.get("answer_times") or {}

        # Fallback wenn Timing fehlt: gib bei korrekt einfach min_points (oder max_points, je nach Geschmack)
        has_timing = isinstance(open_started_at, datetime) and open_duration is not None

        for pid in (players or {}):
            choice = self._extract_choice((answers or {}).get(pid))
            if choice != correct_idx:
                gained[pid] = 0
                continue

            if not has_timing:
                gained[pid] = int(self.min_points)
                continue

            at = answer_times.get(pid)
            if not isinstance(at, datetime):
                # wenn keine Zeit vorhanden: konservativ min_points
                gained[pid] = int(self.min_points)
                continue

            # elapsed in seconds
            elapsed = (at - open_started_at).total_seconds()
            gained[pid] = self._compute_points(elapsed, float(open_duration))

        return gained