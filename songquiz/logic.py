# --- FILE: ./songquiz/logic.py ---
# (Fix: Audio muss immer resolvable sein, sonst nächste Frage.
#  Apple "itunes_no_preview" / "itunes_no_results" -> Eintrag wird aus questions.json gelöscht + protokolliert.)

import os
import random
from datetime import datetime, timezone

from engine.standard_quiz_engine import StandardQuizEngine, StandardQuizTiming
from engine.questions_json import load_json_questions, save_json_questions, lastplayed_ts, now_iso_utc

# Plug-ins
from engine.answers.index import IndexAnswerType
from engine.scoring.time_linear import TimeLinearScoring

# Audio Resolver (Dispatcher für deezer/itunes/local/url)
from engine.audio.resolve_audio import resolve_audio_ref


class PunktesammlerQuestionSource:
    """
    Pro Modul austauschbar:
    - definiert Questions-Pfad (kann auch auf fremde Fragen zeigen)
    - definiert Auswahl-Logik (Picker)
    """

    # Welche Apple-Gründe sollen zu HARD-DELETE führen?
    APPLE_HARD_DELETE_REASONS = {"itunes_no_preview", "itunes_no_results"}

    def __init__(self, questions_path: str):
        self.questions_path = questions_path
        self.base_dir = os.path.dirname(os.path.abspath(self.questions_path))
        self.cleanup_log_path = os.path.join(self.base_dir, "audio_cleanup_log.txt")

    # -----------------------------
    # Logging
    # -----------------------------

    def _utc_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _append_cleanup_log(self, *, q: dict, provider: str, reason: str) -> None:
        """
        Protokolliert Löschungen in ./songquiz/audio_cleanup_log.txt
        """
        try:
            lines = []
            lines.append(f"[{self._utc_iso()}]")
            lines.append(f"REASON: {reason}")
            lines.append(f"PROVIDER: {provider}")
            lines.append(f"QUESTION_ID: {q.get('id')}")
            lines.append("")
            lines.append("QUESTION:")
            lines.append(str(q.get("question") or ""))
            lines.append("")
            lines.append("CORRECT:")
            lines.append(str(q.get("correct") or ""))
            lines.append("")
            lines.append("WRONG:")
            for w in (q.get("wrong") or []):
                lines.append(f"- {w}")
            lines.append("")
            if q.get("title") is not None:
                lines.append(f"TITLE: {q.get('title')}")
            if q.get("artist") is not None:
                lines.append(f"ARTIST: {q.get('artist')}")
            if q.get("audio") is not None:
                lines.append(f"AUDIO_REF: {q.get('audio')}")
            lines.append("-" * 50)
            lines.append("")

            with open(self.cleanup_log_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception:
            # Logging darf den Game-Flow nie blockieren
            pass

    # -----------------------------
    # Auswahl & Audio-Validierung
    # -----------------------------

    def next_question(self) -> dict:
        questions = load_json_questions(self.questions_path)
        if not questions:
            return None

        # Maximalversuche, um eine spielbare Audio-Frage zu finden
        max_tries = 30
        tried_ids = set()

        for _ in range(max_tries):
            # Auswahl-Logik: zufällig aus den X am längsten nicht gespielten
            questions.sort(key=lambda q: (lastplayed_ts(q), int(q.get("id", 0) or 0)))
            pool = questions[:5] if len(questions) > 5 else questions

            # In der Retry-Schleife möglichst nicht ständig dieselbe Frage ziehen
            pool2 = [qq for qq in pool if qq.get("id") not in tried_ids]
            if pool2:
                pool = pool2

            if not pool:
                return None

            q = random.choice(pool)
            tried_ids.add(q.get("id"))

            options = (q.get("wrong") or []) + [q.get("correct")]
            random.shuffle(options)

            audio_ref = q.get("audio")

            # itunes_auto braucht Kontext (title/artist/year)
            title = q.get("title")
            artist = q.get("artist")
            year_val = q.get("year")

            resolved = resolve_audio_ref(
                audio_ref,
                title=title,
                artist=artist,
                year=year_val if year_val not in ("", None) else None,
                local_audio_base_url="/songquiz/media/audio",
                allow_passthrough_urls=True,
            )

            # AUDIO-REGEL: Unabhängig vom Grund: wenn Audio nicht geht -> NICHT ausspielen -> nächste Frage
            if not (resolved and resolved.ok and resolved.url):
                provider = getattr(resolved, "provider", "none") if resolved else "none"
                reason = getattr(resolved, "reason", None) if resolved else "audio_unresolved"
                reason = reason or "audio_unresolved"

                # HARD DELETE: nur bei Apple und nur bei eindeutigen Dauergründen
                if provider == "itunes" and reason in self.APPLE_HARD_DELETE_REASONS:
                    # Protokoll
                    self._append_cleanup_log(q=q, provider=provider, reason=reason)

                    # Eintrag löschen
                    qid = q.get("id")
                    questions = [qq for qq in questions if qq.get("id") != qid]

                    # Speichern
                    save_json_questions(self.questions_path, questions)

                    # Nicht nochmal versuchen
                    tried_ids.add(qid)

                # In jedem Fall: nächste Frage
                continue

            # Erst JETZT als gespielt markieren + speichern (nur wenn Audio wirklich spielbar ist)
            q["lastplayed"] = now_iso_utc()
            save_json_questions(self.questions_path, questions)

            audio_url_or_path = resolved.url

            # year nur zur Laufzeit ergänzen (NICHT speichern)
            year_runtime = year_val
            if (year_runtime in ("", None)) and (resolved.resolved_year is not None):
                year_runtime = resolved.resolved_year

            return {
                "text": q.get("question") or "",
                "options": options,
                "correct_index": options.index(q.get("correct")),
                "audio": audio_url_or_path,
                "image": q.get("image"),
                "year": year_runtime,
                "title": title,
                "artist": artist,
            }

        # Wenn wir hier landen: zu viele nicht spielbare Audio-Refs im Pool/Bank
        return None


class SongquizLogic:
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
        # - Answer-Type
        # - Scoring
        # ---------------------------------------------
        answer_type = IndexAnswerType()
        scoring = TimeLinearScoring(max_points=110, min_points=50)

        self.engine = StandardQuizEngine(
            socketio,
            players,
            on_game_finished=on_game_finished,
            max_rounds=6,
            timing=timing,
            scoring=scoring,
            answer_type=answer_type,
            question_source=question_source,
        )

    # ------- passt zur bisherigen App-Integration -------

    def sync_controller_state(self, sid):
        return self.engine.sync_controller_state(sid)

    def handle_event(self, player_id, action, payload):
        return self.engine.handle_event(player_id, action, payload)

    # Optional: Falls irgendwo (legacy) get_players_ranked genutzt wird
    def get_players_ranked(self):
        return self.engine.players_ranked()
