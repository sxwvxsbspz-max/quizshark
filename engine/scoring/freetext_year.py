# --- FILE: ./engine/scoring/freetext_year.py ---
# Scoring für Freitext-Jahresangaben (z.B. Songyear)
#
# Regeln:
# - Leere / ungültige Antwort -> 0 Punkte
# - Aus Freitext werden die ERSTEN 4 Ziffern extrahiert -> guess_year
# - Vergleich mit question["year"] (correct_year)
# - Punkte:
#     diff 0 -> 400
#     diff 1 -> 200
#     diff 2 -> 100
#     diff 3 -> 50
#     diff 4 -> 25
#     sonst -> 0
#
# Rückgabe:
# - (gained: Dict[player_id, int], details: Dict[player_id, {...}])
#   details enthält für Controller:
#     guess_year, correct_year, diff, points


from typing import Dict, Any, Optional
import re

from engine.scoring.scoring_base import ScoringBase


class FreetextYearScoring(ScoringBase):
    """
    Scoring-Modul für Freitext-Jahresfragen.
    Erwartet:
      - answers[player_id] = Freitext (str oder dict mit text/raw)
      - question["year"] = korrekte Jahreszahl (int oder str)
    """

    # Punktetabelle nach Differenz
    POINTS_BY_DIFF = {
        0: 200,
        1: 100,
        2: 75,
        3: 50,
        4: 25,
    }

    def _extract_guess_year(self, answer: Any) -> Optional[int]:
        """
        Extrahiert die ERSTEN 4 Ziffern aus der Antwort.
        Gibt None zurück, wenn:
          - keine Antwort
          - weniger als 4 Ziffern vorhanden
        """
        if answer is None:
            return None

        # Antwort kann string oder strukturierter Typ sein
        if isinstance(answer, dict):
            text = answer.get("text") or answer.get("raw") or ""
        else:
            text = str(answer)

        if not text:
            return None

        # Alle Ziffernfolgen finden
        digits = re.findall(r"\d", text)
        if len(digits) < 4:
            return None

        year_str = "".join(digits[:4])
        try:
            return int(year_str)
        except ValueError:
            return None

    def _parse_correct_year(self, question: dict) -> Optional[int]:
        """
        Liest das korrekte Jahr aus der Question.
        Erwartet question["year"].
        """
        if not question:
            return None

        year = question.get("year")
        if year in ("", None):
            return None

        try:
            return int(year)
        except (TypeError, ValueError):
            return None

    def compute_gained(
        self,
        *,
        players: Dict[str, dict],
        answers: Dict[str, Any],
        question: dict,
        timing: dict,
    ):
        gained: Dict[str, int] = {}
        details: Dict[str, dict] = {}

        correct_year = self._parse_correct_year(question)

        for player_id in players.keys():
            raw_answer = answers.get(player_id)

            guess_year = self._extract_guess_year(raw_answer)

            if correct_year is None or guess_year is None:
                points = 0
                diff = None
            else:
                diff = abs(guess_year - correct_year)
                points = self.POINTS_BY_DIFF.get(diff, 0)

            gained[player_id] = points

            details[player_id] = {
                "guess_year": guess_year,
                "correct_year": correct_year,
                "diff": diff,
                "points": points,
            }

        return gained, details
