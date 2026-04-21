# --- FILE: ./app_test.py ---
import random
import uuid

import app as prod  # nutzt deine echte app.py (prod.app, prod.socketio, prod.game, ...)


def _ensure_lobby_or_400():
    if prod.current_phase != "lobby":
        return ({"ok": False, "error": "only_in_lobby", "phase": prod.current_phase}, 400)
    return None


def _add_player(name: str, score: int, ready: bool = True):
    # add_player setzt saubere Default-Fields (score=0, answered=False etc.)
    pid = prod.game.add_player(
        sid=f"FAKE_SID_{uuid.uuid4().hex[:8]}",
        name=name
    )

    # Score/Ready überschreiben
    prod.game.players[pid]["score"] = int(score)
    prod.game.players[pid]["ready"] = bool(ready)

    # Ticket-Zuordnung für die aktuelle Runde
    prod.player_run_map[pid] = prod.current_run_id
    return pid


@prod.app.route("/app_test")
def app_test_page():
    # Template liegt im Root (template_folder=".")
    return prod.render_template("apptest.html")


@prod.app.route("/app_test/api/add_player", methods=["POST"])
def api_add_player():
    guard = _ensure_lobby_or_400()
    if guard:
        return guard

    data = prod.request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    score = int(data.get("score") or 0)
    ready = bool(data.get("ready", True))

    if not name:
        return ({"ok": False, "error": "missing_name"}, 400)

    pid = _add_player(name=name, score=score, ready=ready)

    prod.socketio.emit("update_lobby", prod.game.get_player_list())
    return {"ok": True, "player_id": pid, "run_id": prod.current_run_id}


@prod.app.route("/app_test/api/bulk_players", methods=["POST"])
def api_bulk_players():
    guard = _ensure_lobby_or_400()
    if guard:
        return guard

    data = prod.request.get_json(force=True, silent=True) or {}

    n = int(data.get("n") or 0)
    n = max(0, min(n, 100))  # hard cap fürs UI

    min_score = int(data.get("min_score") or 0)
    max_score = int(data.get("max_score") or 0)
    if max_score < min_score:
        min_score, max_score = max_score, min_score

    ready = bool(data.get("ready", True))

    # simple Random-Name-Generator (du kannst später Presets bauen)
    first = ["Alex", "Mira", "Tobi", "Nina", "Chris", "Sam", "Jana", "Ben", "Lea", "Max", "Tina", "Paul"]
    last  = ["K", "M", "S", "R", "B", "H", "L", "N", "P", "T", "F", "G"]

    created = []
    for _ in range(n):
        name = f"{random.choice(first)} {random.choice(last)}."
        score = random.randint(min_score, max_score) if n > 0 else 0
        pid = _add_player(name=name, score=score, ready=ready)
        created.append(pid)

    prod.socketio.emit("update_lobby", prod.game.get_player_list())
    return {"ok": True, "added": len(created), "player_ids": created, "run_id": prod.current_run_id}


@prod.app.route("/app_test/api/reset_lobby", methods=["POST"])
def api_reset_lobby():
    # Reset darf auch außerhalb Lobby Sinn machen – aber du wolltest Testen -> ich lass’s zu
    prod.reset_game_to_lobby()
    prod.socketio.emit("update_lobby", prod.game.get_player_list())
    prod.socketio.emit("switch_phase", {}, room="tv_room")
    prod.socketio.emit("switch_phase", {}, room="controller_room")
    prod.socketio.emit("switch_phase", {}, room="spectator_room")
    return {"ok": True, "phase": prod.current_phase, "run_id": prod.current_run_id}


if __name__ == "__main__":
    # startet identisch wie app.py, aber mit extra Routes
    prod.socketio.run(prod.app, debug=True, host="0.0.0.0", port=8080)
