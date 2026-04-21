# --- FILE: ./engine/answers/index.py ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class IndexAnswerType:
    """
    Standard-Multiple-Choice Answer-Type:
      - erwartet payload {"index": <int>}
      - validiert Range 0..(num_options-1)
      - normalisiert auf int
    """

    def extract(self, payload: Any) -> Optional[int]:
        payload = payload or {}
        idx = payload.get("index", None)
        if idx is None:
            return None
        try:
            return int(idx)
        except Exception:
            return None

    def validate(self, value: Any, *, num_options: int) -> bool:
        try:
            iv = int(value)
        except Exception:
            return False
        if num_options is None:
            return True
        return 0 <= iv < int(num_options)

    def normalize(self, payload: Any, *, num_options: int) -> Optional[int]:
        v = self.extract(payload)
        if v is None:
            return None
        if not self.validate(v, num_options=num_options):
            return None
        return int(v)