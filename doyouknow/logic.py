import os
import random

from engine.standard_quiz_engine import StandardQuizEngine, StandardQuizTiming
from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc
from engine.audio.resolve_audio import resolve_audio_ref

from engine.flows.freetext_doyouknow import FreetextDoYouKnowFlow
from engine.scoring.doyouknow_scoring import DoYouKnowScoring
from engine.answers.text import TextAnswerType


class DoYouKnowQuestionSource:

    def __init__(self, questions_path: str):
        self.questions_path = questions_path

    def next_question(self) -> dict:
        questions = load_json_questions(self.questions_path)
        if not questions:
            return None

        random.shuffle(questions)
        questions.sort(key=lambda q: lastplayed_ts(q))
        pool = questions[:10] if len(questions) > 10 else questions

        q = random.choice(pool)
        q["lastplayed"] = now_iso_utc()
        save_json_questions(self.questions_path, questions)

        audio_ref = q.get("audio")
        audio_url = None
        if audio_ref not in ("", None):
            resolved = resolve_audio_ref(
                audio_ref,
                title=None,
                artist=None,
                year=None,
                local_audio_base_url="/doyouknow/media/audio",
                allow_passthrough_urls=True,
            )
            audio_url = resolved.url

        return {
            "text": q.get("question") or "",
            "audio": audio_url,
            "image": q.get("image") or "",
            "correct": None,
            "alsocorrect": [],
            "answer_spec": {},
            "category": q.get("category"),
            "question_id": q.get("id"),
        }


class DoYouKnowLogic:

    def __init__(self, socketio, players, on_game_finished=None):
        self.socketio = socketio
        self.players = players
        self.on_game_finished = on_game_finished

        questions_path = os.path.join(os.path.dirname(__file__), "questions.json")
        question_source = DoYouKnowQuestionSource(questions_path)

        timing = StandardQuizTiming(
            intro_delay_seconds=3,
            answer_duration_seconds=30,
            reveal_answers_seconds=3,
            resolution_seconds=2,
            scoring_show_points_seconds=2,
            scoring_hold_after_update_seconds=2,
        )

        answer_type = TextAnswerType()
        scoring = DoYouKnowScoring()

        self.engine = StandardQuizEngine(
            socketio,
            players,
            on_game_finished=on_game_finished,
            max_rounds=5,
            timing=timing,
            scoring=scoring,
            answer_type=answer_type,
            question_source=question_source,
            flow_cls=FreetextDoYouKnowFlow,
        )

    def sync_controller_state(self, sid):
        return self.engine.sync_controller_state(sid)

    def handle_event(self, player_id, action, payload):
        return self.engine.handle_event(player_id, action, payload)

    def get_players_ranked(self):
        return self.engine.players_ranked()
