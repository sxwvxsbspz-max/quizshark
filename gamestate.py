# --- FILE: ./gamestate.py ---
import uuid

class GameState:
    def __init__(self, phases):
        # player_id -> playerdata
        self.players = {}

        # sid -> player_id (aktive Socket-Verbindungen)
        self.sid_to_player = {}

        # Phasen kommen AUSSCHLIESSLICH von außen (app.py)
        self.PHASES = list(phases)
        self.current_phase_index = -1

    # --------------------------------------------------
    # RESET HELPERS
    # --------------------------------------------------
    def reset_players(self):
        """
        Jungfräulicher Neustart:
        - alle Spieler löschen
        - alle aktiven SID-Zuordnungen löschen
        """
        self.players = {}
        self.sid_to_player = {}

    # --------------------------------------------------
    # PLAYER HANDLING
    # --------------------------------------------------

    def add_player(self, sid, name):
        """
        Neuer Spieler joint das Spiel.
        Er bekommt eine stabile player_id.
        """
        player_id = str(uuid.uuid4())

        self.players[player_id] = {
            'player_id': player_id,
            'name': name,
            'ready': False,
            'score': 0,
            'answered': False
        }

        self.sid_to_player[sid] = player_id
        return player_id

    def resume_player(self, sid, player_id):
        """
        Spieler kommt mit neuer Socket-ID zurück (Page Reload / Phasenwechsel)
        """
        if player_id in self.players:
            self.sid_to_player[sid] = player_id
            return True
        return False

    def get_player_by_sid(self, sid):
        player_id = self.sid_to_player.get(sid)
        if not player_id:
            return None
        return self.players.get(player_id)

    def get_player_id_by_sid(self, sid):
        return self.sid_to_player.get(sid)

    # --------------------------------------------------
    # ADMIN HELPERS (NEU)
    # --------------------------------------------------
    def toggle_player_ready(self, player_id):
        """
        Toggle ready/unready serverseitig via player_id.
        Rückgabe: neuer ready-status (True/False) oder None wenn player nicht existiert.
        """
        p = self.players.get(player_id)
        if not isinstance(p, dict):
            return None
        p['ready'] = not bool(p.get('ready'))
        return bool(p.get('ready'))

    def remove_player(self, player_id):
        """
        Entfernt einen Spieler sauber:
        - aus players
        - alle SIDs entfernen, die auf diese player_id zeigen
        Rückgabe: True wenn entfernt, sonst False.
        """
        if player_id not in self.players:
            return False

        # Spieler entfernen
        self.players.pop(player_id, None)

        # sid_to_player cleanup (alle SIDs, die auf player_id zeigen)
        try:
            sids_to_drop = [sid for sid, pid in self.sid_to_player.items() if pid == player_id]
            for sid in sids_to_drop:
                self.sid_to_player.pop(sid, None)
        except Exception:
            pass

        return True

    # --------------------------------------------------
    # READY / ANSWER STATES
    # --------------------------------------------------

    def set_player_ready(self, sid):
        player = self.get_player_by_sid(sid)
        if player:
            player['ready'] = True

    def reset_readiness(self):
        for p in self.players.values():
            p['ready'] = False

    def set_player_answered(self, player_id, answered=True):
        if player_id in self.players:
            self.players[player_id]['answered'] = answered

    def reset_answers(self):
        for p in self.players.values():
            p['answered'] = False

    # --------------------------------------------------
    # GAME FLOW
    # --------------------------------------------------

    def all_players_ready(self):
        if not self.players:
            return False
        return all(p['ready'] for p in self.players.values())

    def get_next_phase_name(self):
        self.current_phase_index += 1
        if self.current_phase_index < len(self.PHASES):
            return self.PHASES[self.current_phase_index]
        return None

    # --------------------------------------------------
    # OUTPUT HELPERS
    # --------------------------------------------------

    def get_player_list(self):
        """
        Für Lobby / TV:
        Liefert eine LISTE (nicht dict), damit Frontend stabil bleibt
        """
        return list(self.players.values())

    def get_players_dict(self):
        """
        Für Module (z. B. Punktesammler):
        Liefert dict[player_id] -> playerdata
        """
        return self.players
