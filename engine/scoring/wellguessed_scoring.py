from typing import Dict, Any, Optional, Tuple
from engine.scoring.scoring_base import ScoringBase


class WellGuessedScoring(ScoringBase):
    """
    Scoring für "Gut geschätzt" (WellGuessed).

    - Spieler schätzen einen Zahlenwert
    - Wer am nächsten dran ist: 200 Punkte
    - Wer am weitesten weg ist: 0 Punkte
    - Dazwischen: linear interpoliert
    - Ungültige/leere Antworten: 0 Punkte, werden nicht in die Rangliste einbezogen

    Rückgabe:
    - gained: Dict[player_id, int]
    - details: Dict[player_id, {...}]
      details enthält:
        raw_answer       – roher Eingabe-String
        numeric_answer   – geparste Zahl oder None
        distance         – Abstand zur richtigen Antwort oder None
        correct          – die richtige Zahl (für Anzeige)
        points           – vergebene Punkte
        accepted         – True wenn 200 Punkte, False wenn 0, None dazwischen
    """

    POINTS_MAX = 200
    POINTS_MIN = 0

    def _extract_raw_answer(self, answer: Any) -> str:
        if answer is None:
            return ""
        if isinstance(answer, dict):
            text = answer.get("text")
            if text is None:
                text = answer.get("raw")
            return "" if text is None else str(text)
        return str(answer)

    def _parse_number(self, raw: str) -> Optional[float]:
        if not raw or not raw.strip():
            return None
        try:
            normalized = raw.strip().replace(",", ".").replace(" ", "")
            return float(normalized)
        except (ValueError, TypeError):
            return None

    def compute_gained(
        self,
        *,
        players: Dict[str, dict],
        answers: Dict[str, Any],
        question: dict,
        timing: Any = None,
    ) -> Tuple[Dict[str, int], Dict[str, dict]]:
        gained: Dict[str, int] = {}
        details: Dict[str, dict] = {}

        correct_raw = question.get("correct")
        correct_value = self._parse_number(str(correct_raw)) if correct_raw is not None else None

        if correct_value is None:
            for pid in players:
                gained[pid] = 0
                details[pid] = {
                    "raw_answer": self._extract_raw_answer(answers.get(pid)),
                    "numeric_answer": None,
                    "distance": None,
                    "correct": correct_raw,
                    "points": 0,
                    "accepted": False,
                }
            return gained, details

        player_raw: Dict[str, str] = {}
        player_numeric: Dict[str, Optional[float]] = {}
        player_distance: Dict[str, float] = {}

        for pid in players:
            raw = self._extract_raw_answer(answers.get(pid))
            player_raw[pid] = raw
            num = self._parse_number(raw)
            player_numeric[pid] = num
            if num is not None:
                player_distance[pid] = abs(num - correct_value)

        valid_pids = [pid for pid in players if player_numeric[pid] is not None]

        if not valid_pids:
            for pid in players:
                gained[pid] = 0
                details[pid] = {
                    "raw_answer": player_raw[pid],
                    "numeric_answer": None,
                    "distance": None,
                    "correct": correct_value,
                    "points": 0,
                    "accepted": False,
                }
            return gained, details

        min_dist = min(player_distance[pid] for pid in valid_pids)
        max_dist = max(player_distance[pid] for pid in valid_pids)
        all_tied = (max_dist == min_dist)

        for pid in players:
            if player_numeric[pid] is None:
                points = 0
                accepted = False
            elif all_tied:
                # Alle gültigen Antworten gleich weit weg → alle 200 Punkte
                points = self.POINTS_MAX
                accepted = True
            else:
                dist = player_distance[pid]
                ratio = (max_dist - dist) / (max_dist - min_dist)
                points = round(self.POINTS_MAX * ratio)
                if points == self.POINTS_MAX:
                    accepted = True
                elif points == 0:
                    accepted = False
                else:
                    accepted = None

            gained[pid] = points
            details[pid] = {
                "raw_answer": player_raw[pid],
                "numeric_answer": player_numeric[pid],
                "distance": player_distance.get(pid),
                "correct": correct_value,
                "points": points,
                "accepted": accepted,
            }

        return gained, details
