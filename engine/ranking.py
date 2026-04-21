# --- FILE: ./engine/ranking.py ---

def get_players_ranked(players: dict):
    """
    players: dict[player_id] -> {"name": str, "score": int, ...}
    Returns list of dicts with:
      player_id, name, score, rankdisplay, rank
    Rank ties: same score => same rank.
    """
    items = []
    for pid, p in (players or {}).items():
        items.append({
            "player_id": pid,
            "name": (p.get("name") or ""),
            "score": int(p.get("score", 0) or 0),
        })

    items.sort(key=lambda x: (-x["score"], (x["name"] or "").lower(), x["player_id"]))

    prev_score = None
    prev_rank = None
    for i, it in enumerate(items):
        rankdisplay = i + 1
        score = it["score"]
        if prev_score is None or score != prev_score:
            rank = rankdisplay
        else:
            rank = prev_rank

        it["rankdisplay"] = rankdisplay
        it["rank"] = rank
        prev_score = score
        prev_rank = rank

    return items