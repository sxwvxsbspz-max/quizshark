# --- FILE: ./haveiever/logic.py ---
# (NUR angepasst, um AnswerType + Scoring + HaveIEver-Flow zu verdrahten – sonst unverändert)

import os
import random

from engine.standard_quiz_engine import StandardQuizEngine
from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc

# Plug-ins
from engine.answers.index import IndexAnswerType
from engine.scoring.flat import FlatScoring

# Flow / Timing
from engine.flows.mc_haveiever import MCHaveIEverFlow, HaveIEverTiming


class HaveIEverQuestionSource:
    """
    Pro Modul austauschbar:
    - definiert Questions-Pfad
    - definiert Auswahl-Logik (Picker)
    """

    def __init__(
        self,
        questions_path: str,
        use_standard: bool = True,
        use_adult: bool = False,
        use_boringadult: bool = False,
        use_veryadult: bool = False,
    ):
        self.questions_path = questions_path

        # Kategorie-Flags (Variante B)
        self.use_standard = use_standard
        self.use_adult = use_adult
        self.use_boringadult = use_boringadult
        self.use_veryadult = use_veryadult

    def next_question(self) -> dict:
        questions = load_json_questions(self.questions_path)
        if not questions:
            return None

        # ---------------------------------------------------------
        # Kategorie-Filter (category: "standard" | "adult" | "boringadult" | "veryadult")
        # - wenn category fehlt -> default "standard"
        # - Auswahl gesteuert über use_standard/use_adult/use_boringadult/use_veryadult
        # ---------------------------------------------------------
        filtered = []
        for q in questions:
            cat = (q.get("category") or "standard").strip().lower()

            if cat == "standard" and self.use_standard:
                filtered.append(q)
            elif cat == "adult" and self.use_adult:
                filtered.append(q)
            elif cat == "boringadult" and self.use_boringadult:
                filtered.append(q)
            elif cat == "veryadult" and self.use_veryadult:
                filtered.append(q)

        # Wenn durch Filter nichts übrig bleibt, keine Frage liefern
        if not filtered:
            return None

        # Auswahl-Logik: zufällig aus den X am längsten nicht gespielten
        filtered.sort(key=lambda q: (lastplayed_ts(q), int(q.get("id", 0) or 0)))
        pool = filtered[:2] if len(filtered) > 2 else filtered

        chosen = random.choice(pool)

        # lastplayed MUSS im Original-Array aktualisiert und gespeichert werden
        chosen_id = str(chosen.get("id", ""))
        for q in questions:
            if str(q.get("id", "")) == chosen_id:
                q["lastplayed"] = now_iso_utc()
                break

        save_json_questions(self.questions_path, questions)

        # Have I ever:
        # - poll_text: "Hast du schon mal ...?"
        # - mc_text:   "Wie viele von euch haben schon mal ...?"
        # - pre_audio: "Hast du schon mal" (oder modul-spezifisch)
        # - audio:     "Wie viele von euch ..." (oder modul-spezifisch)
        poll_text = (
            chosen.get("poll_text")
            or chosen.get("poll")
            or chosen.get("pollquestion")
            or chosen.get("poll_question")
            or chosen.get("question")
            or ""
        )

        mc_text = (
            chosen.get("mc_text")
            or chosen.get("mc")
            or chosen.get("mcquestion")
            or chosen.get("mc_question")
            or chosen.get("question")
            or ""
        )

        pre_audio = (
            chosen.get("pre_audio")
            or chosen.get("preaudio")
            or chosen.get("preAudio")
            or ""
        )

        audio = (
            chosen.get("audio")
            or chosen.get("mc_audio")
            or chosen.get("mcaudio")
            or chosen.get("mcAudio")
            or ""
        )

        return {
            # Poll-Phase
            "poll_text": poll_text,

            # MC-Phase (Text wird im Flow genutzt; Optionen/Correct werden nach Poll gebaut)
            "mc_text": mc_text,

            # Audios
            "pre_audio": pre_audio,
            "audio": audio,

            # Optional
            "image": chosen.get("image"),
        }


class HaveieverLogic:
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

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - Kategorien (Variante B: Flags)
        # ---------------------------------------------
        use_standard = True
        use_adult = True
        use_boringadult = True
        use_veryadult = True

        question_source = HaveIEverQuestionSource(
            questions_path,
            use_standard=use_standard,
            use_adult=use_adult,
            use_boringadult=use_boringadult,
            use_veryadult=use_veryadult,
        )

        # ---------------------------------------------
        # PRO MODUL DEFINIERBAR:
        # - timing (inkl. Poll-Block)
        # ---------------------------------------------
        timing = HaveIEverTiming(
            poll_duration_seconds=12.0,
            poll_close_hold_seconds=3.5,
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
        # - Scoring
        # ---------------------------------------------
        answer_type = IndexAnswerType()
        scoring = FlatScoring()

        self.engine = StandardQuizEngine(
            socketio,
            players,
            on_game_finished=on_game_finished,
            max_rounds=8,
            timing=timing,
            scoring=scoring,
            answer_type=answer_type,
            question_source=question_source,
            flow_cls=MCHaveIEverFlow,
        )

    # ------- passt zur bisherigen App-Integration -------

    def sync_controller_state(self, sid):
        return self.engine.sync_controller_state(sid)

    def handle_event(self, player_id, action, payload):
        return self.engine.handle_event(player_id, action, payload)

    # Optional: Falls irgendwo (legacy) get_players_ranked genutzt wird
    def get_players_ranked(self):
        return self.engine.players_ranked()
