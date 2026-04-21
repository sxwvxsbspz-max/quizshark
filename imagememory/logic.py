# --- FILE: ./imagememory/logic.py ---
# (Fork von Punktesammler, erweitert um ImageMemory-Logik:
#  1 Bild pro Runde, max_rounds = Fragen pro Bild)

import os
import random

from engine.standard_quiz_engine import StandardQuizEngine
from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc

# Flow
from engine.flows.mc_memory import MCMemoryFlow, MemoryQuizTiming

# Plug-ins
from engine.answers.index import IndexAnswerType
from engine.scoring.flat import FlatScoring


class ImageMemoryQuestionSource:
    """
    QuestionSource für ImageMemory (JETZT MIT LOGIK):

    - JSON-Struktur:
      [
        {
          image_id, image, audio, lastplayed,
          questions: [{ id, question, correct, wrong, audio, lastplayed }, ...]
        },
        ...
      ]

    - Logik:
      1) Pro Runde genau EIN Bild:
         -> Auswahl aus Top 10 am längsten nicht gespielten Bildern
         -> image.lastplayed wird EINMAL gesetzt (beim ersten Zugriff)
      2) Innerhalb des Bildes:
         -> pro Frage Auswahl aus Top 7 am längsten nicht gespielten Fragen
         -> question.lastplayed wird bei JEDER Frage gesetzt
    """

    def __init__(self, questions_path: str):
        self.questions_path = questions_path

        # Session-State (nur im RAM)
        self._current_image = None
        self._questions_left = 0

    def _load(self):
        return load_json_questions(self.questions_path) or []

    def _save(self, data):
        save_json_questions(self.questions_path, data)

    def _pick_image(self, images: list) -> dict:
        images.sort(key=lambda img: (lastplayed_ts(img), str(img.get("image_id", ""))))
        pool = images[:2] if len(images) > 2 else images
        return random.choice(pool)

    def _pick_question(self, questions: list) -> dict:
        questions.sort(key=lambda q: (lastplayed_ts(q), int(q.get("id", 0) or 0)))
        pool = questions[:4] if len(questions) > 4 else questions
        return random.choice(pool)

    def next_question(self) -> dict:
        data = self._load()
        if not data:
            return None

        # Neues Bild starten?
        if self._current_image is None or self._questions_left <= 0:
            image = self._pick_image(data)

            # Bild-lastplayed setzen (einmal pro Runde)
            image["lastplayed"] = now_iso_utc()
            self._save(data)

            self._current_image = image
            self._questions_left = len(image.get("questions", []))

        image = self._current_image
        questions = image.get("questions") or []
        if not questions:
            return None

        # Frage auswählen
        q = self._pick_question(questions)

        # question-lastplayed sofort setzen
        q["lastplayed"] = now_iso_utc()
        self._save(data)

        self._questions_left -= 1

        options = (q.get("wrong") or []) + [q.get("correct")]
        random.shuffle(options)

        return {
            # Standard-MC
            "text": q.get("question") or "",
            "options": options,
            "correct_index": options.index(q.get("correct")),
            "audio": q.get("audio"),

            # Bild (kann leer sein -> Dummy im Flow)
            "image": image.get("image"),

            # Memo-spezifisch
            "memo_image": image.get("image"),
            "memo_audio": image.get("audio"),
        }


class ImagememoryLogic:
    """
    Wrapper-Logic (API bleibt wie vorher):
      __init__(socketio, players, on_game_finished=None)
      handle_event(player_id, action, payload)
      sync_controller_state(sid)

    WICHTIG:
    - max_rounds = Anzahl Fragen pro Bild (1 Bild pro Runde!)
    """

    def __init__(self, socketio, players, on_game_finished=None):
        self.socketio = socketio
        self.players = players
        self.on_game_finished = on_game_finished

        # ---------------------------------------------
        # Fragenpfad
        # ---------------------------------------------
        questions_path = os.path.join(os.path.dirname(__file__), "questions.json")
        question_source = ImageMemoryQuestionSource(questions_path)

        # ---------------------------------------------
        # Timing (inkl. Memo-Dauer)
        # ---------------------------------------------
        timing = MemoryQuizTiming(
            intro_delay_seconds=3,
            memo_duration_seconds=30,
            answer_duration_seconds=15,
            reveal_answers_seconds=3,
            resolution_seconds=2,
            scoring_show_points_seconds=2,
            scoring_hold_after_update_seconds=2,
        )

        # ---------------------------------------------
        # Answer-Type & Scoring
        # ---------------------------------------------
        answer_type = IndexAnswerType()
        scoring = FlatScoring(points_per_correct=100)

        self.engine = StandardQuizEngine(
            socketio,
            players,
            on_game_finished=on_game_finished,
            max_rounds=6,  # Fragen pro Bild
            timing=timing,
            scoring=scoring,
            answer_type=answer_type,
            question_source=question_source,
            flow_cls=MCMemoryFlow,
        )

    # ------- App-Integration -------

    def sync_controller_state(self, sid):
        return self.engine.sync_controller_state(sid)

    def handle_event(self, player_id, action, payload):
        return self.engine.handle_event(player_id, action, payload)

    def get_players_ranked(self):
        return self.engine.players_ranked()
