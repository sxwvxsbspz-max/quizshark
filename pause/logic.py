from datetime import datetime, timezone, timedelta


class PauseLogic:
    """
    Pause-Modul mit 2 Phasen:

    1) INTRO
       - TV spielt intro.mp4
       - Controller zeigt Startscreen

    2) COUNTDOWN
       - startet erst nach video_finished
       - läuft 300 Sekunden serverseitig
       - TV + Controller zeigen Restzeit synchron an

    Danach automatisch nächstes Modul.
    """

    def __init__(self, socketio, players, on_game_finished=None):
        self.socketio = socketio
        self.players = players
        self.on_game_finished = on_game_finished

        self.state = "INTRO"
        self.duration_seconds = 120

        self.started_at = None
        self.ends_at = None
        self.started_at_iso = None
        self.ends_at_iso = None

        self._finished = False
        self._timer_started = False

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _iso_utc(self, dt):
        if not isinstance(dt, datetime):
            return None
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _intro_payload(self):
        return {
            "state": "INTRO",
        }

    def _countdown_payload(self):
        return {
            "state": "COUNTDOWN",
            "duration": int(self.duration_seconds),
            "started_at": self.started_at_iso,
            "ends_at": self.ends_at_iso,
        }

    def _emit_intro(self, room=None, to=None):
        payload = self._intro_payload()
        if to is not None:
            self.socketio.emit("pause_intro", payload, to=to)
        else:
            self.socketio.emit("pause_intro", payload, room=room)

    def _emit_countdown(self, room=None, to=None):
        payload = self._countdown_payload()
        if to is not None:
            self.socketio.emit("pause_countdown", payload, to=to)
        else:
            self.socketio.emit("pause_countdown", payload, room=room)

    # --------------------------------------------------
    # State handling
    # --------------------------------------------------

    def _start_countdown(self):
        if self._timer_started or self._finished:
            return

        self._timer_started = True
        self.state = "COUNTDOWN"

        self.started_at = datetime.now(timezone.utc)
        self.ends_at = self.started_at + timedelta(seconds=self.duration_seconds)

        self.started_at_iso = self._iso_utc(self.started_at)
        self.ends_at_iso = self._iso_utc(self.ends_at)

        self._emit_countdown(room="tv_room")
        self._emit_countdown(room="controller_room")

        self.socketio.start_background_task(self._timer_task)

    # --------------------------------------------------
    # Reconnect Sync
    # --------------------------------------------------

    def sync_tv_state(self, sid):
        if self.state == "INTRO":
            self._emit_intro(to=sid)
            return

        if self.state == "COUNTDOWN":
            self._emit_countdown(to=sid)

    def sync_controller_state(self, sid):
        if self.state == "INTRO":
            self._emit_intro(to=sid)
            return

        if self.state == "COUNTDOWN":
            self._emit_countdown(to=sid)

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def handle_event(self, player_id, action, payload):
        payload = payload or {}

        if self._finished:
            return

        if action == "video_finished" and self.state == "INTRO":
            self._start_countdown()
            return

    # --------------------------------------------------
    # Timer / Ende
    # --------------------------------------------------

    def _timer_task(self):
        self.socketio.sleep(float(self.duration_seconds))
        self._finish()

    def _finish(self):
        if self._finished:
            return

        self._finished = True
        self.state = "DONE"

        if callable(self.on_game_finished):
            self.on_game_finished()