# --- FILE: ./engine/jokers.py ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


# =========================================================
# Datenmodell
# =========================================================

@dataclass(frozen=True)
class JokerPack:
    white: int
    gold: int


# =========================================================
# Öffentliche API
# =========================================================

def compute_jokers(
    *,
    players_ranked: List[dict],
) -> Dict[str, JokerPack]:
    """
    TEST-MODUS: Joker-Verteilung basiert NUR auf Rank, Score wird ignoriert.

    Regeln:
    - Rank 1: 2G
    - Rank 2: 1G + 1W
    - Rank 3: 2W
    - Rank 4: 1W
    - Rank 5+: 0
    - Gleicher Rank => identische Joker
    """

    if not players_ranked:
        return {}

    def pack_for_rank(rank: int) -> JokerPack:
        if rank == 1:
            return JokerPack(white=0, gold=2)
        if rank == 2:
            return JokerPack(white=1, gold=1)
        if rank == 3:
            return JokerPack(white=2, gold=0)
        if rank == 4:
            return JokerPack(white=1, gold=0)
        return JokerPack(white=0, gold=0)

    result: Dict[str, JokerPack] = {}
    for p in players_ranked:
        pid = p["player_id"]
        rank = int(p["rank"])
        result[pid] = pack_for_rank(rank)

    return result
