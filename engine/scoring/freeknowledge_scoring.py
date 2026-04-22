# --- FILE: ./engine/scoring/freeknowledge_scoring.py ---

import logging
from typing import Dict, Any, Optional, Tuple, List

from engine.scoring.scoring_base import ScoringBase
from engine.scoring import ki_scoring
from engine.text.normalize_answer import normalize_answer

logger = logging.getLogger(__name__)


class FreeKnowledgeScoring(ScoringBase):
    """
    Scoring für FreeKnowledge.

    Regeln:
    - correct = angezeigte Hauptantwort
    - alsocorrect = weitere erlaubte Antworten
    - alles wird normalisiert
    - akzeptiert wird:
        - exakter Match
        - ODER Fuzzy mit genau 1 Edit (ersetzen / löschen / einfügen)
    - richtig = 200 Punkte
    - falsch / leer = 0 Punkte

    Rückgabe:
    - gained: Dict[player_id, int]
    - details: Dict[player_id, {...}]
      details enthält u.a.:
        raw_answer
        normalized_answer
        accepted
        match_type
        matched_answer
        matched_normalized
        points
    """

    POINTS_CORRECT = 200
    POINTS_WRONG = 0

    def _extract_raw_answer(self, answer: Any) -> str:
        if answer is None:
            return ""

        if isinstance(answer, dict):
            text = answer.get("text")
            if text is None:
                text = answer.get("raw")
            return "" if text is None else str(text)

        return str(answer)

    def _get_candidate_answers(self, question: dict) -> List[str]:
        """
        Liefert alle akzeptierten Antworten:
        - zuerst correct
        - dann alsocorrect
        Leere / doppelte Einträge werden entfernt.
        """
        result: List[str] = []

        correct = question.get("correct")
        if correct not in ("", None):
            result.append(str(correct))

        also = question.get("alsocorrect") or []
        if isinstance(also, list):
            for item in also:
                if item not in ("", None):
                    result.append(str(item))

        # Deduplizieren anhand normalisierter Form, Reihenfolge behalten
        seen = set()
        deduped: List[str] = []

        for item in result:
            n = normalize_answer(item)
            if not n:
                continue
            if n in seen:
                continue
            seen.add(n)
            deduped.append(item)

        return deduped

    def _is_one_edit_away(self, a: str, b: str) -> bool:
        """
        True genau dann, wenn Levenshtein-Distanz == 1 ist.
        Erlaubt:
        - 1 Zeichen ersetzt
        - 1 Zeichen gelöscht
        - 1 Zeichen eingefügt
        """
        if a == b:
            return False

        la = len(a)
        lb = len(b)

        if abs(la - lb) > 1:
            return False

        # gleicher Länge -> genau eine Ersetzung
        if la == lb:
            diffs = 0
            for ca, cb in zip(a, b):
                if ca != cb:
                    diffs += 1
                    if diffs > 1:
                        return False
            return diffs == 1

        # sicherstellen: a ist kürzer
        if la > lb:
            a, b = b, a
            la, lb = lb, la

        # jetzt lb == la + 1 -> genau ein Extra-Zeichen in b erlaubt
        i = 0
        j = 0
        used_skip = False

        while i < la and j < lb:
            if a[i] == b[j]:
                i += 1
                j += 1
                continue

            if used_skip:
                return False

            used_skip = True
            j += 1

        return True

    def _find_match(self, normalized_guess: str, candidates: List[str]) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Prüfreihenfolge:
        1. exact match auf irgendeinen Kandidaten
        2. fuzzy match mit genau 1 Edit

        Rückgabe:
        - accepted
        - match_type: "exact" | "fuzzy" | "wrong"
        - matched_answer: ursprüngliche Kandidatenantwort
        - matched_normalized
        """
        if not normalized_guess:
            return False, "wrong", None, None

        normalized_candidates = [
            (candidate, normalize_answer(candidate))
            for candidate in candidates
        ]

        # 1) exact
        for candidate, candidate_norm in normalized_candidates:
            if normalized_guess == candidate_norm:
                return True, "exact", candidate, candidate_norm

        # 2) fuzzy: genau 1 Edit
        for candidate, candidate_norm in normalized_candidates:
            if self._is_one_edit_away(normalized_guess, candidate_norm):
                return True, "fuzzy", candidate, candidate_norm

        return False, "wrong", None, None

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

        display_correct = question.get("correct")
        candidates = self._get_candidate_answers(question)

        # KI-Bewertung versuchen; bei Fehler/Timeout auf lokale Logik zurückfallen
        player_answers = {
            pid: self._extract_raw_answer(answers.get(pid))
            for pid in players
        }
        ai_results: Optional[Dict[str, bool]] = None
        try:
            ai_results = ki_scoring.evaluate_answers(question, player_answers)
            logger.debug("KI-Bewertung erfolgreich")
        except Exception as exc:
            logger.warning("KI-Bewertung fehlgeschlagen, Fallback auf lokal: %s", exc)

        for player_id in players.keys():
            raw_answer = player_answers[player_id]
            normalized_answer = normalize_answer(raw_answer)

            if ai_results is not None:
                accepted = ai_results.get(player_id, False)
                match_type = "ai"
                matched_answer = display_correct if accepted else None
                matched_normalized = None
                evaluation_method = "ai"
            else:
                accepted, match_type, matched_answer, matched_normalized = self._find_match(
                    normalized_answer,
                    candidates,
                )
                evaluation_method = "local"

            points = self.POINTS_CORRECT if accepted else self.POINTS_WRONG
            gained[player_id] = points

            details[player_id] = {
                "raw_answer": raw_answer,
                "normalized_answer": normalized_answer,
                "accepted": accepted,
                "match_type": match_type,
                "matched_answer": matched_answer,
                "matched_normalized": matched_normalized,
                "correct": display_correct,
                "points": points,
                "evaluation_method": evaluation_method,
            }

        return gained, details