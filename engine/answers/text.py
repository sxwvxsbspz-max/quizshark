# --- FILE: ./engine/answers/text.py ---
from __future__ import annotations

from typing import Any, Optional

from engine.answers.answer_base import AnswerTypeBase


class TextAnswerType(AnswerTypeBase):
    """
    Minimaler Freitext-AnswerType.
    Erwartet im payload z.B.:
      { "text": "1999" }  oder { "year": "1999" } oder { "value": "1999" }

    normalize(...) gibt einen String zurück (trimmed).
    """

    def __init__(
        self,
        *,
        min_len: int = 1,
        max_len: int = 128,
        to_lower: bool = False,
        digits_only: bool = False,
    ):
        self.min_len = int(min_len)
        self.max_len = int(max_len)
        self.to_lower = bool(to_lower)
        self.digits_only = bool(digits_only)

    def normalize(self, payload: Any, num_options: int = 0) -> Optional[str]:
        # payload robust lesen
        text = ""
        if isinstance(payload, dict):
            v = payload.get("text")
            if v is None:
                v = payload.get("year")
            if v is None:
                v = payload.get("value")
            if v is None:
                v = payload.get("answer")
            text = "" if v is None else str(v)
        else:
            text = "" if payload is None else str(payload)

        text = text.strip()

        if self.digits_only:
            text = "".join(ch for ch in text if ch.isdigit())

        if self.to_lower:
            text = text.lower()

        if len(text) < self.min_len:
            return None

        if len(text) > self.max_len:
            text = text[: self.max_len]

        return text
