# --- FILE: ./finale/logic.py ---
# (NUR angepasst, um den neuen Finale-Flow (Sudden Death) zu nutzen – sonst unverändert)

import os
import random
from typing import Optional

from engine.standard_quiz_engine import StandardQuizEngine, StandardQuizTiming
from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc

# NEU: Finale Sudden-Death Flow
from engine.flows.finale import FinaleFlow

# NEU: Plug-ins
from engine.answers.index import IndexAnswerType
from engine.scoring.flat import FlatScoring


class FinaleQuestionSource:
    """
    Pro Modul austauschbar:
    - definiert Questions-Pfad (kann auch auf fremde Fragen zeigen)
    - definiert Auswahl-Logik (Picker)
    """

    def __init__(
        self,
        questions_path: str,
        *,
        easy_until_round: int = 2,
        medium_until_round: int = 7,
        hard_until_round: int = 9,
        pool_size: int = 50,
        fallback_to_any: bool = True,
    ):
        """
        Difficulty-Routing:
          rounds 1..easy_until_round        => difficulty="easy"
          rounds (easy_until+1)..medium    => difficulty="medium"
          rounds (medium_until+1)..hard    => difficulty="hard"
          rounds (hard_until+1)..          => difficulty="veryhard"

        fallback_to_any:
          Wenn in der gewünschten Difficulty keine Fragen verfügbar sind,
          wird (falls True) auf die komplette Liste zurückgefallen.
        """
        self.questions_path = questions_path
        self.easy_until_round = int(easy_until_round or 0)
        self.medium_until_round = int(medium_until_round or 0)
        self.hard_until_round = int(hard_until_round or 0)
        self.pool_size = int(pool_size or 0)
        self.fallback_to_any = bool(fallback_to_any)

    def _difficulty_for_round(self, round_index: int) -> str:
        r = int(round_index or 0)
        if r <= self.easy_until_round:
            return "easy"
        if r <= self.medium_until_round:
            return "medium"
        if r <= self.hard_until_round:
            return "hard"
        return "veryhard"

    def _safe_id_int(self, q: dict) -> int:
        """
        IDs müssen NICHT zwingend int sein. Wir nutzen sie nur als Tie-Breaker.
        - numerische Strings wie "00012" -> ok
        - nicht-numerisch -> 0 (stabile Sortierung über lastplayed bleibt trotzdem)
        """
        v = q.get("id", 0)
        try:
            return int(v or 0)
        except Exception:
            return 0

    def next_question(self, round_index: Optional[int] = None) -> Optional[dict]:
        questions = load_json_questions(self.questions_path)
        if not questions:
            return None

        # Ziel-Difficulty anhand Round bestimmen (round_index kommt jetzt aus FinaleFlow)
        diff = self._difficulty_for_round(int(round_index or 0))

        # Erst filtern nach difficulty
        filtered = [q for q in questions if (q.get("difficulty") or "").lower() == diff]

        # Fallback: wenn Segment leer (oder difficulty-Feld noch nicht gepflegt)
        candidates = filtered if filtered else (questions if self.fallback_to_any else [])

        if not candidates:
            return None

        # Auswahl: zufällig aus den X am längsten nicht gespielten (innerhalb candidates)
        candidates_sorted = sorted(
            candidates,
            key=lambda q: (lastplayed_ts(q), self._safe_id_int(q)),
        )

        if self.pool_size and len(candidates_sorted) > self.pool_size:
            pool = candidates_sorted[: self.pool_size]
        else:
            pool = candidates_sorted

        chosen = random.choice(pool)

        # lastplayed setzen & speichern
        chosen["lastplayed"] = now_iso_utc()
        save_json_questions(self.questions_path, questions)

        options = (chosen.get("wrong") or []) + [chosen.get("correct")]
        random.shuffle(options)

        correct = chosen.get("correct")
        try:
            correct_index = options.index(correct)
        except ValueError:
            correct_index = 0

        return {
            "text": chosen.get("question") or "",
            "options": options,
            "correct_index": int(correct_index),
            "audio": chosen.get("audio"),
            "image": chosen.get("image"),
            # optional hilfreich fürs Debugging:
            "difficulty": diff,
        }


class FinaleLogic:
    """
    Wrapper-Logic (API bleibt wie vorher):
      __init__(socketio, players, on_game_finished=None)
      handle_event(player_id, action, payload)
      sync_controller_state(sid)
    """

    def __init__(self, socketio, players, on_game_finished=None):
        self.socketio = socketio
        self.players = players
        self.on_game_finished = on_game_finished

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - Fragenpfad
        # ---------------------------------------------
        questions_path = os.path.join(os.path.dirname(__file__), "questions.json")

        # Difficulty-Konfiguration fürs Finale:
        # 1-2 easy, 3-7 medium, 8-9 hard, ab 10 veryhard
        question_source = FinaleQuestionSource(
            questions_path,
            easy_until_round=3,
            medium_until_round=7,
            hard_until_round=11,
            pool_size=5,
            fallback_to_any=True,
        )

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - timing
        # ---------------------------------------------
        timing = StandardQuizTiming(
            intro_delay_seconds=3,
            answer_duration_seconds=10,
            reveal_answers_seconds=3,
            resolution_seconds=2,
            scoring_show_points_seconds=2,
            scoring_hold_after_update_seconds=2,
        )

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - Answer-Type
        # - Scoring
        # ---------------------------------------------
        answer_type = IndexAnswerType()
        scoring = FlatScoring(points_per_correct=100)

        self.engine = StandardQuizEngine(
            socketio,
            players,
            on_game_finished=on_game_finished,
            max_rounds=9999,
            timing=timing,
            scoring=scoring,
            answer_type=answer_type,
            question_source=question_source,
            flow_cls=FinaleFlow,
        )

    # ------- passt zur bisherigen App-Integration -------

    def sync_controller_state(self, sid):
        return self.engine.sync_controller_state(sid)

    # Optional: TV-Sync (app.py ruft das, wenn vorhanden)
    def sync_tv_state(self, sid):
        if hasattr(self.engine.flow, "sync_tv_state"):
            return self.engine.flow.sync_tv_state(sid)
        return None

    def handle_event(self, player_id, action, payload):
        return self.engine.handle_event(player_id, action, payload)

    # Optional: Falls irgendwo (legacy) get_players_ranked genutzt wird
    def get_players_ranked(self):
        return self.engine.players_ranked()
