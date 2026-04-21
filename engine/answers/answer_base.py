# --- FILE: ./engine/answers/answer_base.py ---

from __future__ import annotations

from typing import Any, Optional


class AnswerTypeBase:
    """
    Basis-Interface für Answer-Types.

    Ein Answer-Type ist zuständig für:
      - Extraktion aus payload
      - Validierung
      - Normalisierung (das, was intern gespeichert wird)

    Engine nutzt IMMER normalize().
    """

    def extract(self, payload: Any) -> Optional[Any]:
        raise NotImplementedError

    def validate(self, value: Any, **kwargs) -> bool:
        raise NotImplementedError

    def normalize(self, payload: Any, **kwargs) -> Optional[Any]:
        raise NotImplementedError