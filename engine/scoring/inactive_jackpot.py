# --- FILE: ./engine/scoring/jackpot.py ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class JackpotScoring:
    """
    Jackpot-Scoring (pro Frage):
      - Start-Jackpot = #Mitspieler * base_per_player
      - Falsche Antwort:
          * Spieler verliert bis zu wrong_penalty Punkte (aber nie unter 0)
          * genau der tatsächlich verlorene Betrag wandert in den Jackpot
      - Richtige Antwort:
          * teilt sich am Ende den Jackpot gleichmäßig mit allen anderen Richtigen
      - Keine Antwort / Enthaltung:
          * 0 Punkte (kein Abzug, kein Jackpot-Effekt)

    Erwartetes Answer-Format (Standard MC):
      answers[player_id] = int (choice index)
      oder answers[player_id] = {"value": int, ...}
    """

    base_per_player: int = 50
    wrong_penalty: int = 100

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
        players = players or {}
        answers = answers or {}

        correct_idx = int(question.get("correct_index"))
        gained: Dict[str, int] = {pid: 0 for pid in players.keys()}

        # 1) Start-Jackpot
        jackpot = int(len(players) * int(self.base_per_player))

        winners = []

        # 2) Erst klassifizieren: richtig / falsch / enthaltung
        for pid in players.keys():
            raw = answers.get(pid, None)

            # Enthaltung / keine Antwort => 0
            if raw is None:
                continue

            choice = self._extract_choice(raw)
            if choice is None:
                # Ungültig behandeln wie Enthaltung (neutral)
                continue

            if int(choice) == int(correct_idx):
                winners.append(pid)
                continue

            # Falsch: Abzug bis max wrong_penalty, aber nie unter 0
            current_score = int(players.get(pid, {}).get("score", 0) or 0)
            penalty = min(int(self.wrong_penalty), max(0, current_score))

            if penalty > 0:
                gained[pid] -= int(penalty)
                jackpot += int(penalty)

        # 3) Jackpot auf Gewinner verteilen
        if winners:
            winners_sorted = sorted(winners)
            share = int(jackpot // len(winners_sorted))
            remainder = int(jackpot % len(winners_sorted))

            for i, pid in enumerate(winners_sorted):
                gained[pid] += share + (1 if i < remainder else 0)

        return gained
