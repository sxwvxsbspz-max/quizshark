# --- FILE: ./engine/jokers.py ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import math


# =========================================================
# Datenmodell
# =========================================================

@dataclass(frozen=True)
class JokerPack:
    white: int
    gold: int


# Stärke-Reihenfolge (wichtig: NICHT Anzahl, sondern Wertigkeit)
# schwach -> stark
TIER_ORDER: List[JokerPack] = [
    JokerPack(white=1, gold=0),  # 1W
    JokerPack(white=2, gold=0),  # 2W
    JokerPack(white=1, gold=1),  # 1W + 1G
    JokerPack(white=0, gold=2),  # 2G
]


# =========================================================
# interne Helpers
# =========================================================

def _tier_of(pack: JokerPack) -> int:
    for i, p in enumerate(TIER_ORDER):
        if p == pack:
            return i
    raise ValueError(f"Unknown JokerPack {pack}. Add it to TIER_ORDER.")


def _max_pack(a: JokerPack, b: JokerPack) -> JokerPack:
    """Gibt das stärkere JokerPack zurück (niemals Downgrade)."""
    return a if _tier_of(a) >= _tier_of(b) else b


# =========================================================
# Öffentliche API
# =========================================================

def compute_jokers(
    *,
    players_ranked: List[dict],
) -> Dict[str, JokerPack]:
    """
    Berechnet Joker pro Spieler anhand des finalen Rankings.

    Erwartetes Input-Format (aus engine/ranking.py):
      players_ranked = [
        {
          "player_id": str,
          "score": int,
          "rank": int,
          "rankdisplay": int,
          ...
        },
        ...
      ]

    WICHTIGE REGELN:
    - Gleicher Score => gleicher Rank => IDENTISCHE Joker
    - Garantien gelten pro RANG, nicht pro Index
    - Gibt es z.B. mehrere Rank-2-Spieler, bekommen ALLE Rank-2-Joker
    - Existiert kein Rank 3, werden KEINE Rank-3-Garantien vergeben

    Sonderfälle:
    - 1 Spieler: 0 Joker (Finale automatisch gewonnen)

    Ab 2 Spielern (Decile-Logik):
    - gap = top_score - bottom_score
    - gap == 0 -> alle 1W
    - sonst:
        Score-Bänder in Zehnteln (boundary gehört zum besseren Band):
          Top 1/10      -> 2G
          Nächste 2/10  -> 1G + 1W
          Nächste 3/10  -> 2W
          Rest          -> 1W

    Mindest-Garantien (als UPGRADE, niemals Downgrade):
    - Rank 1: mindestens 2G
    - Rank 2: mindestens 1W + 1G
    - Rank 3: mindestens 2W
    - Letzter: mindestens 1W
    """

    if not players_ranked:
        return {}

    # Gruppiere Spieler nach Rank
    by_rank: Dict[int, List[dict]] = {}
    for p in players_ranked:
        by_rank.setdefault(int(p["rank"]), []).append(p)

    ranks_sorted = sorted(by_rank.keys())
    n_players = len(players_ranked)

    # --------------------------------------------------
    # Sonderfälle
    # --------------------------------------------------

    # 1 Spieler -> keine Joker
    if n_players == 1:
        p = players_ranked[0]
        return {p["player_id"]: JokerPack(white=0, gold=0)}

    # --------------------------------------------------
    # Ab 2 Spielern: Decile-Logik
    # --------------------------------------------------

    scores = [int(p["score"]) for p in players_ranked]
    top_score = max(scores)
    bottom_score = min(scores)
    gap = top_score - bottom_score

    # Alle gleich -> alle 1W
    if gap == 0:
        result = {
            p["player_id"]: JokerPack(white=1, gold=0)
            for p in players_ranked
        }
    else:
        width = gap / 10.0
        eps = 1e-12 * max(1.0, abs(width))

        def decile_for_score(score: int) -> int:
            d = top_score - score
            raw = (d - eps) / width
            idx = int(math.floor(raw))
            return max(0, min(9, idx))

        def pack_for_decile(idx: int) -> JokerPack:
            if idx < 1:          # Top 1/10
                return JokerPack(white=0, gold=2)
            if idx < 3:          # Next 2/10
                return JokerPack(white=1, gold=1)
            if idx < 6:          # Next 3/10
                return JokerPack(white=2, gold=0)
            return JokerPack(white=1, gold=0)

        # Basis-Zuordnung pro Spieler
        result: Dict[str, JokerPack] = {}
        for p in players_ranked:
            base = pack_for_decile(decile_for_score(int(p["score"])))
            result[p["player_id"]] = base

    # --------------------------------------------------
    # Mindest-Garantien pro RANG (gleichbehandelt!)
    # --------------------------------------------------

    # Rank 1 Garantie: mindestens 2G
    if 1 in by_rank:
        for p in by_rank[1]:
            pid = p["player_id"]
            result[pid] = _max_pack(result[pid], JokerPack(white=0, gold=2))

    # Rank 2 Garantie: mindestens 1W + 1G
    if 2 in by_rank:
        for p in by_rank[2]:
            pid = p["player_id"]
            result[pid] = _max_pack(result[pid], JokerPack(white=1, gold=1))

    # Rank 3 Garantie (nur wenn Rank 3 existiert): mindestens 2W
    if 3 in by_rank:
        for p in by_rank[3]:
            pid = p["player_id"]
            result[pid] = _max_pack(result[pid], JokerPack(white=2, gold=0))

    # Letzter Rank: mindestens 1W
    last_rank = max(ranks_sorted)
    for p in by_rank[last_rank]:
        pid = p["player_id"]
        result[pid] = _max_pack(result[pid], JokerPack(white=1, gold=0))

    return result
