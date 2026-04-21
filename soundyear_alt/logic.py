# --- FILE: ./soundyear/logic.py ---
# (Umgestellt auf Freetext-Year: FreetextStandardFlow + FreetextYearScoring + TextAnswerType
#  Audio-Resolver-Dispatcher + itunes_auto/year-runtime bleibt erhalten)

import os
import random

from engine.standard_quiz_engine import StandardQuizEngine, StandardQuizTiming
from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc

# NEU: Freitext-Flow + Plug-ins
from engine.flows.freetext_standard import FreetextStandardFlow
from engine.scoring.freetext_year import FreetextYearScoring

# Answer-Type (Freitext)
from engine.answers.text import TextAnswerType

# Audio Resolver (Dispatcher für deezer/itunes/local/url)
from engine.audio.resolve_audio import resolve_audio_ref


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
        pool = questions[:5] if len(questions) > 5 else questions

        q = random.choice(pool)
        q["lastplayed"] = now_iso_utc()
        save_json_questions(self.questions_path, questions)

        audio_ref = q.get("audio")

        # itunes_auto braucht Kontext (title/artist/year)
        title = q.get("title")
        artist = q.get("artist")
        year_val = q.get("year")

        # Resolver liefert URL + optional resolved_year (nur wenn year leer ist)
        resolved = resolve_audio_ref(
            audio_ref,
            title=title,
            artist=artist,
            year=year_val if year_val not in ("", None) else None,
            local_audio_base_url="/soundyear/media/audio",
            allow_passthrough_urls=True,
        )
        audio_url_or_path = resolved.url

        # year nur zur Laufzeit ergänzen (NICHT speichern)
        year_runtime = year_val
        if (year_runtime in ("", None)) and (resolved.resolved_year is not None):
            year_runtime = resolved.resolved_year

        # Wichtig:
        # FreetextStandardFlow sendet unveil_correct mit {"correct": ...}
        # Wenn "correct" nicht gesetzt ist, kommt im TV/Frontend "—" an.
        return {
            "text": q.get("question") or "",
            "audio": audio_url_or_path,
            "image": q.get("image"),

            # Freitext-Jahr: korrektes Ergebnis explizit setzen
            "year": year_runtime,
            "correct": year_runtime,
            "answer_spec": {"year": year_runtime},

            # Optionaler Kontext (Debug/Audio)
            "title": title,
            "artist": artist,
        }


class SoundyearLogic:
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
        question_source = PunktesammlerQuestionSource(questions_path)

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - timing
        # ---------------------------------------------
        timing = StandardQuizTiming(
            intro_delay_seconds=3,
            answer_duration_seconds=28,
            reveal_answers_seconds=3,
            resolution_seconds=2,
            scoring_show_points_seconds=2,
            scoring_hold_after_update_seconds=2,
        )

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - Answer-Type (Freitext)
        # - Scoring (Year-Distance)
        # ---------------------------------------------
        answer_type = TextAnswerType()
        scoring = FreetextYearScoring()

        self.engine = StandardQuizEngine(
            socketio,
            players,
            on_game_finished=on_game_finished,
            max_rounds=7,
            timing=timing,
            scoring=scoring,
            answer_type=answer_type,
            question_source=question_source,
            flow_cls=FreetextStandardFlow,  # <- NEU
        )

    # ------- passt zur bisherigen App-Integration -------

    def sync_controller_state(self, sid):
        return self.engine.sync_controller_state(sid)

    def handle_event(self, player_id, action, payload):
        return self.engine.handle_event(player_id, action, payload)

    # Optional: Falls irgendwo (legacy) get_players_ranked genutzt wird
    def get_players_ranked(self):
        return self.engine.players_ranked()
