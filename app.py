# --- FILE: ./app.py ---

from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from gamestate import GameState

from datetime import datetime, timezone

from modules import get_modules, get_phase_sequence
from lobby.logic import LobbyLogic  # Lobby-Join-Logik ausgelagert

# NEU: Admin-Backend-Logik ausgelagert
from admin.logic import build_admin_state, handle_admin_action

import os
import uuid
import time

app = Flask(__name__, template_folder=".")
app.config['SECRET_KEY'] = 'quiz_secret_99'
socketio = SocketIO(app, cors_allowed_origins="*")

MODULES = get_modules()

# --------------------------------------------------
# Phasen aus Registry (intro bleibt bewusst fix)
# --------------------------------------------------
game = GameState(phases=get_phase_sequence())
current_module = None

# Aktuelle Phase (URL bleibt stabil)
# START: Pre-Lobby beim Einschalten
current_phase = "pre_lobby"

# --------------------------------------------------
# RUN-ID (Ticket pro Spielrunde)
# --------------------------------------------------
current_run_id = uuid.uuid4().hex
# player_id -> run_id (in welcher Runde wurde der Spieler angelegt)
player_run_map = {}

# --------------------------------------------------
# LobbyLogic Instanz
# --------------------------------------------------
lobby_logic = LobbyLogic(game)

# --------------------------------------------------
# Admin-Gate für Spielstart
# --------------------------------------------------
admin_go = False

# --------------------------------------------------
# Post-Game Return Phase (default: lobby)
# --------------------------------------------------
post_game_phase = "lobby"

# --------------------------------------------------
# Throttle für "video_finished" pro RUN-ID
# --------------------------------------------------
VIDEO_FINISHED_COOLDOWN_SEC = 1.0
_last_video_finished_by_run = {}  # run_id -> timestamp (time.time())

# =========================
# ADMIN STATE HELPERS
# =========================
def _admin_state_payload():
    return build_admin_state(
        game=game,
        current_phase=current_phase,
        admin_go=admin_go,
        post_game_phase=post_game_phase,
        current_module=current_module,
    )

def emit_admin_state(*, to_sid=None):
    payload = _admin_state_payload()
    if to_sid:
        socketio.emit("admin_state", payload, to=to_sid)
        return
    socketio.emit("admin_state", payload, room="admin_room")


# =========================
# Generisches Modul-Static
# =========================
@app.route('/<phase>/static/<path:filename>')
def phase_static(phase, filename):
    allowed_ext = (
        '.css', '.js', '.map',
        '.png', '.jpg', '.jpeg', '.svg', '.webp',
        '.woff', '.woff2', '.ttf'
    )
    if not filename.lower().endswith(allowed_ext):
        return ("Not Found", 404)

    static_dir = os.path.join(app.root_path, phase, 'static')
    return send_from_directory(static_dir, filename)

# =========================
# STABILE ROOT-URLS
# =========================
def render_tv_for_phase(phase):
    if phase == "lobby":
        return render_template("lobby/tv.html")
    if phase == "pre_lobby":
        return render_template("pre_lobby/tv.html")
    return render_template(f"{phase}/tv.html")

def render_controller_for_phase(phase):
    if phase == "lobby":
        return render_template("lobby/controller.html")
    if phase == "pre_lobby":
        return render_template("pre_lobby/controller.html")
    return render_template(f"{phase}/controller.html")

@app.route('/tv')
def tv_root():
    return render_tv_for_phase(current_phase)

@app.route('/')
@app.route('/play')
def controller_root():
    return render_controller_for_phase(current_phase)

# =========================
# PHASE-URLS (bleiben bestehen)
# =========================
@app.route('/<phase>/tv')
def phase_tv(phase):
    return render_template(f'{phase}/tv.html')

@app.route('/<phase>/controller')
def phase_controller(phase):
    return render_template(f'{phase}/controller.html')

# =========================
# Modul-Media
# =========================
@app.route('/<phase>/media/<path:filename>')
def phase_media(phase, filename):
    return send_from_directory(os.path.join(app.root_path, phase, 'media'), filename)

# =========================
# ROOT-MEDIA (Option B)
# =========================
@app.route("/media/<path:filename>")
def media(filename):
    media_dir = os.path.join(app.root_path, "media")
    return send_from_directory(media_dir, filename)

# =========================
# PLAYERDATA (z.B. /playerdata/playersounds/map.json)
# =========================
@app.route("/playerdata/<path:filename>")
def playerdata(filename):
    playerdata_dir = os.path.join(app.root_path, "playerdata")
    return send_from_directory(playerdata_dir, filename)

# =========================
# ADMIN (Testseite: /admin -> /admin/admin.html)
# =========================
@app.route("/admin")
def admin():
    admin_dir = os.path.join(app.root_path, "admin")
    return send_from_directory(admin_dir, "admin.html")

# =========================
# RESET HELPERS
# =========================
def reset_game_to_lobby():
    global current_module, current_phase, current_run_id, player_run_map, admin_go, post_game_phase
    current_module = None

    # Post-Game Return Phase (default lobby)
    current_phase = post_game_phase or "lobby"

    game.current_phase_index = -1
    game.reset_readiness()
    game.reset_answers()

    # komplette Lobby "jungfräulich" machen
    game.players = {}
    game.sid_to_player = {}

    # neue Spielrunde -> neues Ticket
    current_run_id = uuid.uuid4().hex

    # alte Zuordnungen auslaufen lassen
    player_run_map = {}

    # Admin-Go beim Reset immer aus
    admin_go = False

    # Admin-State push
    emit_admin_state()

# =========================
# GAME FINISHED CALLBACK
# =========================
def on_module_game_finished():
    trigger_next_phase()

# =========================
# SOCKETS
# =========================
@socketio.on('register_tv')
def handle_tv_reg():
    join_room('tv_room')

    # Serverzeit für Clock-Sync (ms seit Epoch, UTC)
    emit('server_time', {'server_now': int(datetime.now(timezone.utc).timestamp() * 1000)}, to=request.sid)

    # Snapshot direkt nach TV-Register
    emit('update_lobby', game.get_player_list(), to=request.sid)

    # Reconnect direkt in laufenden Modul-State (TV)
    global current_module, current_phase
    if current_module and hasattr(current_module, "sync_tv_state"):
        try:
            current_module.sync_tv_state(request.sid)
        except Exception as e:
            print("sync_tv_state failed:", e)

@socketio.on('register_controller')
def handle_controller_reg(data=None):
    """
    Controller-Reg:
    - In pre_lobby/lobby: Controller-Room immer ok; wenn player_id+run_id passen,
      mappen wir SID->player_id sofort (damit Admin-Pushes sicher ankommen).
    - Im laufenden Spiel: nur wenn player_id + run_id korrekt (Ticket).
      Sonst: spectator_room + 'too_late' Event, KEIN sync_controller_state.
    """
    global current_module, current_phase, current_run_id, player_run_map

    data = data or {}
    player_id = (data.get('player_id') or '').strip()
    run_id    = (data.get('run_id') or '').strip()

    # Immer Controller-Room + server_time
    join_room('controller_room')
    emit('server_time', {'server_now': int(datetime.now(timezone.utc).timestamp() * 1000)}, to=request.sid)

    # Pre-Lobby / Lobby: falls möglich sofort SID mappen (Race-Fix für Admin-Events)
    if current_phase in ("pre_lobby", "lobby"):
        if (
            player_id and run_id and
            (run_id == current_run_id) and
            (player_run_map.get(player_id) == current_run_id) and
            (player_id in (game.players or {}))
        ):
            try:
                game.resume_player(request.sid, player_id)
            except Exception:
                pass
        return

    # Ab hier: Spiel läuft -> Ticket prüfen
    if (not player_id) or (not run_id) or (run_id != current_run_id):
        join_room('spectator_room')
        emit('too_late', {'phase': current_phase}, to=request.sid)
        return

    # player_id muss zur aktuellen Runde gehören
    if player_run_map.get(player_id) != current_run_id:
        join_room('spectator_room')
        emit('too_late', {'phase': current_phase}, to=request.sid)
        return

    # Spieler muss existieren
    if player_id not in (game.players or {}):
        join_room('spectator_room')
        emit('too_late', {'phase': current_phase}, to=request.sid)
        return

    # SID auf Player mappen (Reconnect/Reload)
    game.resume_player(request.sid, player_id)

    # Reconnect direkt in laufenden Modul-State (Controller)
    if current_module and hasattr(current_module, "sync_controller_state"):
        try:
            current_module.sync_controller_state(request.sid)
        except Exception as e:
            print("sync_controller_state failed:", e)

@socketio.on("register_admin")
def handle_admin_reg():
    join_room("admin_room")
    emit_admin_state(to_sid=request.sid)

@socketio.on('join_game')
def handle_join(data):
    global current_phase, current_run_id, player_run_map

    # Join nur in Lobby erlaubt (Pre-Lobby: geschlossen)
    if current_phase != "lobby":
        emit('join_ack', {'ok': False, 'error': 'lobby_closed'}, to=request.sid)
        return

    data = data or {}

    name = (data.get('name') or '').strip()
    incoming_player_id = (data.get('player_id') or '').strip()

    resp = lobby_logic.handle_join(
        sid=request.sid,
        name=name,
        incoming_player_id=incoming_player_id,
        current_run_id=current_run_id,
        player_run_map=player_run_map,
    )

    emit('join_ack', resp, to=request.sid)

    if resp and resp.get('ok'):
        socketio.emit('update_lobby', game.get_player_list())
        emit_admin_state()

@socketio.on('resume_player')
def handle_resume(data):
    global current_phase, current_run_id, player_run_map

    player_id = (data.get('player_id') or '').strip()
    run_id    = (data.get('run_id') or '').strip()

    if not player_id:
        emit('resume_ack', {'ok': False, 'error': 'missing_player_id'}, to=request.sid)
        return

    if (not run_id) or (run_id != current_run_id):
        emit('resume_ack', {'ok': False, 'error': 'stale_session'}, to=request.sid)
        return

    if player_run_map.get(player_id) != current_run_id:
        emit('resume_ack', {'ok': False, 'error': 'stale_session'}, to=request.sid)
        return

    ok = game.resume_player(request.sid, player_id)
    if not ok:
        emit('resume_ack', {'ok': False, 'error': 'unknown_player_id'}, to=request.sid)
        return

    player = game.players.get(player_id)

    socketio.emit('update_lobby', game.get_player_list())
    emit(
        'resume_ack',
        {
            'ok': True,
            'player_id': player_id,
            'name': player.get('name') if player else '',
            'run_id': current_run_id,
            'ready': bool(player.get('ready')) if player else False,
        },
        to=request.sid
    )

    emit('server_time', {'server_now': int(datetime.now(timezone.utc).timestamp() * 1000)}, to=request.sid)

    global current_module
    if current_module and hasattr(current_module, "sync_controller_state"):
        try:
            current_module.sync_controller_state(request.sid)
        except Exception as e:
            print("sync_controller_state failed:", e)

@socketio.on('player_ready')
def handle_ready():
    global current_phase, admin_go

    # Ready nur in Lobby
    if current_phase != "lobby":
        return

    game.set_player_ready(request.sid)
    socketio.emit('update_lobby', game.get_player_list())

    emit_admin_state()

    if admin_go and game.all_players_ready():
        trigger_next_phase()

@socketio.on('video_finished')
def handle_video_finished(data=None):
    global current_run_id, _last_video_finished_by_run

    now = time.time()
    last = _last_video_finished_by_run.get(current_run_id, 0)

    if (now - last) < VIDEO_FINISHED_COOLDOWN_SEC:
        print(
            "video_finished IGNORED (cooldown)",
            "| sid:", request.sid,
            "| phase:", current_phase,
            "| run_id:", current_run_id,
            "| dt:", round(now - last, 3),
            "| referrer:", request.headers.get("Referer"),
        )
        return

    _last_video_finished_by_run[current_run_id] = now

    print(
        "video_finished ACCEPTED",
        "| sid:", request.sid,
        "| phase:", current_phase,
        "| run_id:", current_run_id,
        "| referrer:", request.headers.get("Referer"),
        "| ua:", request.headers.get("User-Agent"),
    )
    trigger_next_phase()

@socketio.on('game_finished')
def handle_game_finished():
    reset_game_to_lobby()
    socketio.emit('update_lobby', game.get_player_list())
    socketio.emit('switch_phase', {}, room='tv_room')
    socketio.emit('switch_phase', {}, room='controller_room')
    socketio.emit('switch_phase', {}, room='spectator_room')
    emit_admin_state()

def trigger_next_phase():
    global current_module, current_phase, admin_go

    next_phase = game.get_next_phase_name()
    if not next_phase:
        reset_game_to_lobby()
        socketio.emit('update_lobby', game.get_player_list())
        socketio.emit('switch_phase', {}, room='tv_room')
        socketio.emit('switch_phase', {}, room='controller_room')
        socketio.emit('switch_phase', {}, room='spectator_room')
        emit_admin_state()
        return

    # Admin-Go "verbrauchen", sobald wir die Lobby verlassen
    if current_phase == "lobby":
        admin_go = False
        emit_admin_state()

    current_phase = next_phase

    if next_phase == "intro":
        current_module = None
    else:
        mod = MODULES.get(next_phase) or {}
        LogicCls = mod.get("logic")
        if LogicCls:
            current_module = LogicCls(
                socketio,
                game.get_players_dict(),
                on_game_finished=on_module_game_finished
            )
        else:
            current_module = None

    socketio.emit('switch_phase', {}, room='tv_room')
    socketio.emit('switch_phase', {}, room='controller_room')

    emit_admin_state()

@socketio.on('module_event')
def handle_module_event(data):
    global current_module, current_run_id, player_run_map, current_phase, admin_go, post_game_phase

    data = data or {}
    action = data.get('action')
    payload = data.get('payload', {}) or {}

    if not action:
        return

    scope = (data.get('scope') or '').strip().lower()

    SYSTEM_ACTIONS = {
        "video_finished",
        "announcement_finished",
        "timer_expired",
        "unveil_finished",
        "module_finished",
        "memo_finished",
        "request_pause",
        "resume_pause",
        "resolution_finished",
        "awardjokers_reveal",
        # ADMIN / FLOW
        "admin_set_phase",
        "admin_go_on",
        "admin_go_off",
        "admin_abort",
        "admin_set_post_game_phase",
        "admin_state_request",
        # ADMIN / PLAYERS
        "admin_toggle_ready",
        "admin_remove_player",
    }

    if not scope:
        scope = "system" if action in SYSTEM_ACTIONS else "player"

    # --------------------------------------------------
    # ADMIN / FLOW (system actions, auch wenn current_module None)
    # --------------------------------------------------
    if scope == "system":
        # State request bleibt hier, weil to_sid benötigt wird
        if action == "admin_state_request":
            emit_admin_state(to_sid=request.sid)
            return

        handled, updates = handle_admin_action(
            action=action,
            payload=payload,
            game=game,
            current_phase=current_phase,
            admin_go=admin_go,
            post_game_phase=post_game_phase,
            current_module=current_module,
            current_run_id=current_run_id,
            player_run_map=player_run_map,
            lobby_logic_cls=LobbyLogic,
            socketio=socketio,
            emit_admin_state=emit_admin_state,
            trigger_next_phase=trigger_next_phase,
        )

        if handled:
            # Updates (wenn vorhanden) zurück in die Globals schreiben
            if isinstance(updates, dict):
                if "current_phase" in updates:
                    current_phase = updates["current_phase"]
                if "admin_go" in updates:
                    admin_go = bool(updates["admin_go"])
                if "post_game_phase" in updates:
                    post_game_phase = updates["post_game_phase"]
                if "current_module" in updates:
                    current_module = updates["current_module"]
            return

        # Ab hier: normale system-actions an Module, falls vorhanden
        if not current_module:
            return
        current_module.handle_event(None, action, payload)
        return

    # --------------------------------------------------
    # scope == "player" (oder unbekannt -> wie player behandeln)
    # --------------------------------------------------
    if not current_module:
        return

    player_id = game.get_player_id_by_sid(request.sid)
    if not player_id:
        return

    # nur Player der aktuellen Runde dürfen Module-Events senden
    if player_run_map.get(player_id) != current_run_id:
        return

    current_module.handle_event(player_id, action, payload)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8080)
