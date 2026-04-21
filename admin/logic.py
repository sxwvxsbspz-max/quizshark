# --- FILE: ./admin/logic.py ---

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple, List


def build_admin_state(
    *,
    game,
    current_phase: str,
    admin_go: bool,
    post_game_phase: str,
    current_module,
) -> Dict[str, Any]:
    """
    Baut den Payload für 'admin_state'.

    Erwartet:
      - game.players: dict[player_id] -> playerdata (mindestens: player_id, name, ready)
      - current_module: None oder Logic-Instanz
    """
    players_total = 0
    ready_total = 0
    players_list: List[Dict[str, Any]] = []

    try:
        players_dict = (game.players or {})
        players_total = len(players_dict)
        ready_total = sum(1 for p in players_dict.values() if (p or {}).get("ready"))
        # Liste für Admin UI (sortiert nach Name, case-insensitive)
        for p in players_dict.values():
            if not isinstance(p, dict):
                continue
            players_list.append(
                {
                    "player_id": p.get("player_id"),
                    "name": (p.get("name") or "").strip(),
                    "ready": bool(p.get("ready")),
                }
            )
        players_list.sort(key=lambda x: (x.get("name") or "").casefold())
    except Exception:
        pass

    return {
        "current_phase": current_phase,
        "admin_go": bool(admin_go),
        "post_game_phase": post_game_phase or "lobby",
        "module_running": bool(current_module),
        "players_total": players_total,
        "ready_total": ready_total,
        # neu: für die Admin-Spielerliste
        "players": players_list,
    }


def handle_admin_action(
    *,
    action: str,
    payload: Dict[str, Any],
    # --- state (Input/Output über Rückgabe-Updates) ---
    game,
    current_phase: str,
    admin_go: bool,
    post_game_phase: str,
    current_module,
    current_run_id: str,
    player_run_map: Dict[str, str],
    # --- dependencies ---
    lobby_logic_cls=None,
    socketio=None,
    # --- callbacks (von app.py geliefert) ---
    emit_admin_state: Optional[Callable[..., None]] = None,
    trigger_next_phase: Optional[Callable[[], None]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Verarbeitet admin_* Actions.

    Rückgabe:
      (handled: bool, updates: dict)

    'updates' enthält ggf. neue Werte für:
      - current_phase
      - admin_go
      - post_game_phase
      - current_module

    Außerdem werden (wenn socketio/emit_admin_state vorhanden) die passenden Emits gemacht.
    """
    if not action:
        return False, {}

    payload = payload or {}
    updates: Dict[str, Any] = {}

    def _emit_admin():
        if callable(emit_admin_state):
            emit_admin_state()

    def _refresh_screens(*, include_spectators: bool = True):
        if not socketio:
            return
        # Lobby-Liste (TV/Controller)
        try:
            socketio.emit("update_lobby", game.get_player_list())
        except Exception:
            pass
        # Phase-Refresh
        try:
            socketio.emit("switch_phase", {}, room="tv_room")
            socketio.emit("switch_phase", {}, room="controller_room")
            if include_spectators:
                socketio.emit("switch_phase", {}, room="spectator_room")
        except Exception:
            pass

    def _sids_for_player(player_id: str) -> List[str]:
        """
        GameState hat nur sid -> player_id.
        Für Admin-Updates brauchen wir den Reverse-Lookup.
        """
        if not player_id:
            return []
        out: List[str] = []
        try:
            for sid, pid in (game.sid_to_player or {}).items():
                if pid == player_id:
                    out.append(sid)
        except Exception:
            pass
        return out

    # ---------------------------------------------
    # STATE REQUEST
    # ---------------------------------------------
    if action == "admin_state_request":
        # handled in app.py normalerweise (emit to_sid=request.sid).
        # Hier: wir signalisieren nur "handled", app.py kann weiterhin selbst to_sid bedienen.
        return True, {}

    # ---------------------------------------------
    # POST GAME RETURN
    # ---------------------------------------------
    if action == "admin_set_post_game_phase":
        desired = (payload.get("phase") or "").strip()
        if desired not in ("pre_lobby", "lobby"):
            return True, {}
        updates["post_game_phase"] = desired
        _emit_admin()
        return True, updates

    # ---------------------------------------------
    # ABORT (während Spiel erlaubt)
    # ---------------------------------------------
    if action == "admin_abort":
        desired = (payload.get("phase") or "").strip() or "lobby"
        if desired not in ("pre_lobby", "lobby"):
            desired = "lobby"

        # Modul sofort stoppen
        updates["current_module"] = None

        # Phase-Sequence zurücksetzen
        try:
            game.current_phase_index = -1
        except Exception:
            pass

        # Spieler behalten, aber "Lobby-like" zurücksetzen
        try:
            game.reset_answers()
        except Exception:
            pass
        try:
            game.reset_readiness()
        except Exception:
            pass

        # Falls du LobbyLogic._reset_player_fields nutzen willst: (optional injected)
        if lobby_logic_cls is not None:
            try:
                for p in (game.players or {}).values():
                    if not isinstance(p, dict):
                        continue
                    lobby_logic_cls._reset_player_fields(p, name=None)
            except Exception:
                pass

        # Admin-Go zurücknehmen
        updates["admin_go"] = False

        # In gewünschte Phase springen
        updates["current_phase"] = desired

        # UI refresh
        _refresh_screens(include_spectators=True)
        _emit_admin()
        return True, updates

    # ---------------------------------------------
    # PHASE SET (nur wenn kein Modul läuft)
    # ---------------------------------------------
    if action == "admin_set_phase":
        if current_module:
            return True, {}
        desired = (payload.get("phase") or "").strip()
        if desired not in ("pre_lobby", "lobby"):
            return True, {}
        updates["current_phase"] = desired

        _refresh_screens(include_spectators=True)
        _emit_admin()
        return True, updates

    # ---------------------------------------------
    # GO ON/OFF (nur wenn kein Modul läuft)
    # ---------------------------------------------
    if action == "admin_go_on":
        if current_module:
            return True, {}
        updates["admin_go"] = True
        _emit_admin()

        # Wenn bereits alle ready und in Lobby -> direkt starten
        if (current_phase == "lobby") and callable(trigger_next_phase):
            try:
                if game.all_players_ready():
                    trigger_next_phase()
            except Exception:
                pass
        return True, updates

    if action == "admin_go_off":
        if current_module:
            return True, {}
        updates["admin_go"] = False
        _emit_admin()
        return True, updates

    # ---------------------------------------------
    # PLAYER READY TOGGLE (auch während Spiel erlaubt)
    # ---------------------------------------------
    if action == "admin_toggle_ready":
        player_id = (payload.get("player_id") or "").strip()
        if not player_id:
            return True, {}

        # SIDs dieses Players VOR dem Toggle ermitteln (kann mehrere geben)
        sids = _sids_for_player(player_id)

        # Toggle, und neuen Status ermitteln
        new_ready = None

        # bevorzugt: GameState helper, sonst fallback direkt
        if hasattr(game, "toggle_player_ready"):
            try:
                new_ready = game.toggle_player_ready(player_id)
            except Exception:
                new_ready = None
        else:
            try:
                if player_id in (game.players or {}):
                    p = game.players[player_id]
                    if isinstance(p, dict):
                        p["ready"] = not bool(p.get("ready"))
                        new_ready = bool(p.get("ready"))
            except Exception:
                new_ready = None

        # Betroffenen Controller sofort updaten (damit UI umspringt)
        if socketio and (new_ready is not None) and sids:
            for sid in sids:
                try:
                    socketio.emit(
                        "admin_player_ready_state",
                        {"ready": bool(new_ready)},
                        to=sid
                    )
                except Exception:
                    pass

        # TV/Controller sollen es sehen
        if socketio:
            try:
                socketio.emit("update_lobby", game.get_player_list())
            except Exception:
                pass

        _emit_admin()
        return True, {}

    # ---------------------------------------------
    # PLAYER REMOVE (auch während Spiel erlaubt)
    # ---------------------------------------------
    if action == "admin_remove_player":
        player_id = (payload.get("player_id") or "").strip()
        if not player_id:
            return True, {}

        # SIDs VOR dem Remove einsammeln
        sids = _sids_for_player(player_id)

        # Betroffenen Controller informieren (damit er UI zurücksetzt / localStorage löscht)
        if socketio and sids:
            for sid in sids:
                try:
                    socketio.emit("admin_player_removed", {}, to=sid)
                except Exception:
                    pass

        # Mapping (Ticket) aufräumen
        try:
            player_run_map.pop(player_id, None)
        except Exception:
            pass

        # bevorzugt: GameState helper, sonst fallback direkt
        if hasattr(game, "remove_player"):
            try:
                game.remove_player(player_id)
            except Exception:
                pass
        else:
            # fallback: players + sid_to_player cleanup
            try:
                if player_id in (game.players or {}):
                    game.players.pop(player_id, None)
                # sid_to_player: alle SIDs entfernen, die auf player_id zeigen
                sids_to_drop = []
                for sid, pid in (game.sid_to_player or {}).items():
                    if pid == player_id:
                        sids_to_drop.append(sid)
                for sid in sids_to_drop:
                    game.sid_to_player.pop(sid, None)
            except Exception:
                pass

        # Screens updaten (TV/Controller/Spectator bleiben in ihrer Phase, aber Lobby-Liste muss stimmen)
        if socketio:
            try:
                socketio.emit("update_lobby", game.get_player_list())
            except Exception:
                pass
            # Optional: Controller des entfernten Spielers könnte noch verbunden sein;
            # Register/Ticket-Checks im Spiel verhindern dann Events, aber UI ist außerhalb scope.

        _emit_admin()
        return True, {}

    return False, {}
