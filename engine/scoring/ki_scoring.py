import json
import os
import threading
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_API_KEY_PATH = os.path.join(PROJECT_ROOT, "openaiapi.json")

_MODEL = "gpt-4o-mini"
_MAX_TOKENS = 300


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


def _build_prompt(question: dict, player_answers: dict) -> str:
    question_text = question.get("question", "")
    correct = question.get("correct", "")
    also = question.get("alsocorrect") or []

    also_text = ""
    if also:
        also_text = f"\nWeitere akzeptierte Antworten: {', '.join(str(a) for a in also if a)}"

    answers_lines = "\n".join(
        f'  "{pid}": "{answer}"' for pid, answer in player_answers.items()
    )

    example = "{" + ", ".join(f'"{pid}": true' for pid in player_answers) + "}"

    return (
        f"Du bewertest Antworten in einem Quizspiel.\n\n"
        f"Frage: {question_text}\n"
        f"Richtige Antwort: {correct}"
        f"{also_text}\n\n"
        f"Spielerantworten:\n{answers_lines}\n\n"
        f"Bewertungsregeln:\n"
        f"- Großzügig bei Rechtschreibfehlern und Tippfehlern\n"
        f"- Akzeptiere sinngemäß richtige Antworten (Kurzformen, alternative Schreibweisen)\n"
        f"- Lehne eindeutig falsche Antworten ab\n"
        f"- Leere Antworten sind immer falsch\n\n"
        f"Antworte NUR mit einem JSON-Objekt ohne Markdown, z.B.: {example}"
    )


def _do_api_call(question: dict, player_answers: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=_load_api_key())
    prompt = _build_prompt(question, player_answers)

    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()

    # JSON aus der Antwort extrahieren (falls doch Markdown dabei)
    if "```" in raw:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end]

    parsed = json.loads(raw)

    if not isinstance(parsed, dict):
        raise ValueError(f"Unerwartetes Antwortformat: {raw}")

    return {pid: bool(parsed.get(pid, False)) for pid in player_answers}


def evaluate_answers(
    question: dict,
    player_answers: dict,
    timeout: int = 8,
) -> dict:
    """
    Bewertet alle Spielerantworten einer Runde via KI.

    Gibt {player_id: bool} zurück oder wirft eine Exception bei Fehler/Timeout.
    Der Aufrufer soll bei Exception auf die lokale Auswertung zurückfallen.
    """
    if not player_answers:
        return {}

    result: list = [None]
    error: list = [None]

    def _run():
        try:
            result[0] = _do_api_call(question, player_answers)
        except Exception as exc:
            error[0] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        raise TimeoutError(f"KI-Bewertung Timeout nach {timeout}s")

    if error[0] is not None:
        raise error[0]

    return result[0]
