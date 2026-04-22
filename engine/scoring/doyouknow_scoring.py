import json
import logging
import os
import threading
from typing import Any, Dict, List, Tuple

from engine.scoring.scoring_base import ScoringBase

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_API_KEY_PATH = os.path.join(PROJECT_ROOT, "openaiapi.json")
_MODEL = "gpt-4o-mini"
_MAX_TOKENS = 400
_KI_TIMEOUT = 15


class KiTimeoutAbort(Exception):
    """KI timed out or failed — caller should abort the module."""
    pass


def _load_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        return api_key
    if not os.path.exists(_API_KEY_PATH):
        raise RuntimeError(f"openaiapi.json nicht gefunden: {_API_KEY_PATH}")
    with open(_API_KEY_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    key = (cfg.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY fehlt/leer in openaiapi.json")
    return key


def _build_prompt(question_text: str, player_answers: dict) -> str:
    answers_lines = "\n".join(
        f'  "{pid}": "{answer}"' for pid, answer in player_answers.items()
    )
    pids = list(player_answers.keys())
    example = json.dumps(
        {
            "results": {pid: True for pid in pids},
            "examples": ["Antwort1", "Antwort2", "Antwort3"],
        },
        ensure_ascii=False,
    )
    return (
        f"Du bewertest Antworten in einem Quizspiel. Die Frage hat viele mögliche richtige Antworten.\n\n"
        f"Frage: {question_text}\n\n"
        f"Spielerantworten:\n{answers_lines}\n\n"
        f"Bewertungsregeln:\n"
        f"- Bewertet wird, ob die Antwort inhaltlich korrekt auf die Frage passt\n"
        f"- Großzügig bei Rechtschreibfehlern und Tippfehlern\n"
        f"- Akzeptiere alternative Schreibweisen und Kurzformen\n"
        f"- Leere Antworten sind immer falsch\n\n"
        f"Gib außerdem bis zu 3 Beispielantworten: bevorzuge korrekte Spielerantworten, "
        f"ergänze mit eigenen Vorschlägen falls nötig.\n\n"
        f"Antworte NUR mit einem JSON-Objekt ohne Markdown, z.B.: {example}"
    )


def _do_api_call(question_text: str, player_answers: dict) -> Tuple[dict, List[str]]:
    from openai import OpenAI

    client = OpenAI(api_key=_load_api_key())
    prompt = _build_prompt(question_text, player_answers)

    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end]

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"Unerwartetes Format: {raw}")

    results_raw = parsed.get("results", {})
    results = {pid: bool(results_raw.get(pid, False)) for pid in player_answers}

    examples_raw = parsed.get("examples", [])
    examples = [str(e) for e in examples_raw if e][:3]

    return results, examples


class DoYouKnowScoring(ScoringBase):
    POINTS_CORRECT = 100
    POINTS_WRONG = 0

    def _extract_raw_answer(self, answer: Any) -> str:
        if answer is None:
            return ""
        if isinstance(answer, dict):
            text = answer.get("text") or answer.get("raw")
            return "" if text is None else str(text)
        return str(answer)

    def compute_gained(
        self,
        *,
        players: Dict[str, dict],
        answers: Dict[str, Any],
        question: dict,
        timing: dict,
    ):
        question_text = question.get("text") or question.get("question") or ""

        player_answers = {
            pid: self._extract_raw_answer(answers.get(pid))
            for pid in players
        }

        result: list = [None]
        error: list = [None]

        def _run():
            try:
                result[0] = _do_api_call(question_text, player_answers)
            except Exception as exc:
                error[0] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=_KI_TIMEOUT)

        if thread.is_alive():
            raise KiTimeoutAbort(f"KI-Bewertung Timeout nach {_KI_TIMEOUT}s")

        if error[0] is not None:
            raise KiTimeoutAbort(f"KI-Bewertung Fehler: {error[0]}")

        ki_results, ki_examples = result[0]

        gained: Dict[str, int] = {}
        details: Dict[str, dict] = {}

        for player_id in players.keys():
            raw_answer = player_answers[player_id]
            accepted = ki_results.get(player_id, False)
            points = self.POINTS_CORRECT if accepted else self.POINTS_WRONG
            gained[player_id] = points
            details[player_id] = {
                "raw_answer": raw_answer,
                "accepted": accepted,
                "match_type": "ai",
                "points": points,
                "evaluation_method": "ai",
            }

        details["_examples"] = ki_examples[:3]

        return gained, details
