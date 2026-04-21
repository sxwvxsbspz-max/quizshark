# --- FILE: ./vollereinsatz/logic.py ---
# (NUR angepasst, um AnswerType + Scoring + VollerEinsatz-Flow zu verdrahten – sonst unverändert)

import os
import random

from engine.standard_quiz_engine import StandardQuizEngine
from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc

# NEU: Plug-ins
from engine.answers.index import IndexAnswerType
from engine.scoring.wagered import WageredScoring

# NEU: Flow / Timing
from engine.flows.mc_voller_einsatz import MCVollerEinsatzFlow, VollerEinsatzTiming


class PunktesammlerQuestionSource:
    """
    Pro Modul austauschbar:
    - definiert Questions-Pfad (kann auch auf fremde Fragen zeigen)
    - definiert Auswahl-Logik (Picker)
    """

    def __init__(self, questions_path: str):
        self.questions_path = questions_path

    def next_question(self) -> dict:
        questions = load_json_questions(self.questions_path)
        if not questions:
            return None

        # Auswahl-Logik: zufällig aus den X am längsten nicht gespielten
        questions.sort(key=lambda q: (lastplayed_ts(q), int(q.get("id", 0) or 0)))
        pool = questions[:50] if len(questions) > 50 else questions

        q = random.choice(pool)
        q["lastplayed"] = now_iso_utc()
        save_json_questions(self.questions_path, questions)

        options = (q.get("wrong") or []) + [q.get("correct")]
        random.shuffle(options)

        return {
            "text": q.get("question") or "",
            "options": options,
            "correct_index": options.index(q.get("correct")),
            "audio": q.get("audio"),
            "image": q.get("image"),
            "category": q.get("category"),
            "categoryaudio": q.get("categoryaudio"),
        }


class VollereinsatzLogic:
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
        # - Fragenpfad (Punktesammler wiederverwenden)
        # ---------------------------------------------
        questions_path = os.path.join(os.path.dirname(__file__), "questions.json")
        question_source = PunktesammlerQuestionSource(questions_path)


        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - timing (inkl. Wager-Block)
        # ---------------------------------------------
        timing = VollerEinsatzTiming(
            category_intro_seconds=2.0,
            wager_duration_seconds=15.0,
            wager_unveil_seconds=2.0,
            intro_delay_seconds=3,
            answer_duration_seconds=15,
            reveal_answers_seconds=3,
            resolution_seconds=2,
            scoring_show_points_seconds=2,
            scoring_hold_after_update_seconds=2,
            no_points_hold_seconds=5.0,
        )

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - Answer-Type
        # - Scoring (Wagered, clamp >= 0 im Plugin)
        # ---------------------------------------------
        answer_type = IndexAnswerType()
        scoring = WageredScoring(default_wager=25)

        self.engine = StandardQuizEngine(
            socketio,
            players,
            on_game_finished=on_game_finished,
            max_rounds=6,
            timing=timing,
            scoring=scoring,
            answer_type=answer_type,
            question_source=question_source,
            flow_cls=MCVollerEinsatzFlow,
        )

    # ------- passt zur bisherigen App-Integration -------

    def sync_controller_state(self, sid):
        return self.engine.sync_controller_state(sid)

    def handle_event(self, player_id, action, payload):
        return self.engine.handle_event(player_id, action, payload)

    # Optional: Falls irgendwo (legacy) get_players_ranked genutzt wird
    def get_players_ranked(self):
        return self.engine.players_ranked()
