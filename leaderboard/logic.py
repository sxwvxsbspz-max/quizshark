# --- FILE: ./leaderboard/logic.py ---
from datetime import datetime, timezone


class LeaderboardLogic:
    """
    Einfaches Leaderboard-Modul:
    - zeigt das Ranking (mit Rank-Ties bei gleichen Scores)
    - TV ist Timing-Master
    - TV meldet am Ende per "module_finished" (modulagnostisch)
    - Backend beendet dann sofort und signalisiert dem TV/Controller die Rückkehr in die Lobby
    """

    def __init__(self, socketio, players, on_game_finished=None):
        self.socketio = socketio
        self.players = players  # dict[player_id] -> playerdata (shared)
        self.on_game_finished = on_game_finished

        # Zustände:
        # SHOWING    -> Leaderboard läuft / wird angezeigt
        # DONE       -> fertig
        self.state = "SHOWING"

        # "duration" wird weiterhin im Payload geliefert (als Hint / Fallback).
        self.show_seconds = 30

        self._started = False

        # Finish-Tracking (damit module_finished nicht mehrfach triggert)
        self._finish_scheduled = False

        # direkt starten
        self._start_show()

    # --------------------------------------------------
    # Ranking (mit Ties)
    # --------------------------------------------------

    def get_players_ranked(self):
        items = []
        for pid, p in self.players.items():
            items.append({
                "player_id": pid,
                "name": p.get("name", ""),
                "score": int(p.get("score", 0) or 0),
            })

        # Sort: Score desc, Name asc, ID asc (stabil)
        items.sort(key=lambda x: (-x["score"], (x["name"] or "").lower(), x["player_id"]))

        prev_score = None
        prev_rank = None
        for i, it in enumerate(items):
            rankdisplay = i + 1
            score = it["score"]

            # gleiche Punkte => gleicher Rang
            if prev_score is None or score != prev_score:
                rank = rankdisplay
            else:
                rank = prev_rank

            it["rankdisplay"] = rankdisplay
            it["rank"] = rank

            prev_score = score
            prev_rank = rank

        return items

    # --------------------------------------------------
    # Start / Emits / Reconnect
    # --------------------------------------------------

    def _start_show(self):
        if self._started:
            return
        self._started = True
        self.state = "SHOWING"

        players_ranked = self.get_players_ranked()

        # direkt anzeigen
        self._emit_leaderboard(room="tv_room", players_ranked=players_ranked)
        self._emit_leaderboard(room="controller_room", players_ranked=players_ranked)

        # Sicherheitsnetz: falls nie ein "module_finished" kommt
        self.socketio.start_background_task(self._watchdog_finish_task)

    def _emit_leaderboard(self, room=None, to=None, players_ranked=None):
        payload = {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "players_ranked": players_ranked if players_ranked is not None else self.get_players_ranked(),
            "duration": self.show_seconds,
        }
        if to is not None:
            self.socketio.emit("show_leaderboard", payload, to=to)
        else:
            self.socketio.emit("show_leaderboard", payload, room=room)

    def sync_tv_state(self, sid):
        # bei Reload im Leaderboard: einfach erneut das Board an den TV schicken
        if self.state == "SHOWING":
            self._emit_leaderboard(to=sid)

    def sync_controller_state(self, sid):
        # bei Reload im Leaderboard: einfach erneut das Board an den Controller schicken
        if self.state == "SHOWING":
            self._emit_leaderboard(to=sid)

    # --------------------------------------------------
    # Public Event Handler (TV Done)
    # --------------------------------------------------

    def handle_event(self, player_id, action, payload):
        """
        Erwartet Events vom TV.
        action:
          - "module_finished" -> Frontend (TV) hat Hold+Fade abgeschlossen und ist fertig.
          - "unveil_finished" -> Legacy/Alias: wird wie module_finished behandelt.
        """
        if self.state != "SHOWING":
            return

        if action not in ("module_finished", "unveil_finished"):
            return

        # nur einmal beenden
        if self._finish_scheduled:
            return

        self._finish_scheduled = True
        self.state = "DONE"
        self.end_game()

    # --------------------------------------------------
    # Watchdog
    # --------------------------------------------------

    def _watchdog_finish_task(self):
        # Sicherheitsnetz: nach 30s beenden, falls Events fehlen
        self.socketio.sleep(30.0)

        if self.state != "SHOWING":
            return

        self.state = "DONE"
        self.end_game()

    def end_game(self):
        # Erst ggf. serverseitigen Abschluss (Phase/State/etc.)
        if callable(self.on_game_finished):
            self.on_game_finished()

        # Dann dem TV + Controller signalisieren: zurück zur Lobby
        self.socketio.emit("game_finished", {}, room="tv_room")
        self.socketio.emit("game_finished", {}, room="controller_room")