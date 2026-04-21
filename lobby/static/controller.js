// --- FILE: ./lobby/static/controller.js ---

const LS_PLAYER_ID_KEY   = "blitzquiz_player_id";
const LS_PLAYER_NAME_KEY = "blitzquiz_player_name";
const LS_RUN_ID_KEY      = "blitzquiz_run_id";

let joinInFlight = false;

// =====================================================
// ROOM REGISTRATION (FIX)
// =====================================================
// Problem: base.html verbindet den Socket (io()) schon, bevor dieses File geladen ist.
// Dann feuert 'connect' nicht mehr -> register_controller wurde nie gesendet -> kein controller_room -> kein switch_phase.
// Fix: Registrierung sowohl bei 'connect' als auch sofort, falls schon connected.

function registerControllerNow(){
  try {
    const pid = (localStorage.getItem(LS_PLAYER_ID_KEY) || "").trim();
    const rid = (localStorage.getItem(LS_RUN_ID_KEY) || "").trim();
    socket.emit('register_controller', { player_id: pid, run_id: rid });
  } catch (e) {
    // niemals crashen
  }
}

socket.on('connect', () => {
  registerControllerNow();
  attemptResumeIfPossible();
});

// Falls socket schon connected ist, wenn dieses Script geladen wird:
if (socket && socket.connected) {
  registerControllerNow();
  // Resume nicht doppelt: attemptResumeIfPossible() guarded über joinInFlight
  attemptResumeIfPossible();
}

// ---------------- UI HELPERS ----------------

function setJoinEnabled(enabled){
  const btn = document.getElementById('join-btn');
  if (!btn) return;
  btn.disabled = !enabled;
}

function focusNameInput(selectAll=true){
  const el = document.getElementById('name-input');
  if (!el) return;
  el.focus();
  if (selectAll) el.select();
}

function showSetup() {
  document.getElementById('setup-area').style.display = 'block';
  document.getElementById('ready-area').style.display = 'none';
  document.getElementById('wait-area').style.display  = 'none';
}

function showReady(name) {
  document.getElementById('player-name-display').innerText = name || "";
  document.getElementById('setup-area').style.display = 'none';
  document.getElementById('ready-area').style.display = 'block';
  document.getElementById('wait-area').style.display  = 'none';
}

function showWait() {
  document.getElementById('setup-area').style.display = 'none';
  document.getElementById('ready-area').style.display = 'none';
  document.getElementById('wait-area').style.display  = 'block';
}

// ---------------- RESUME ----------------

function attemptResumeIfPossible(){
  if (joinInFlight) return;

  const pid = (localStorage.getItem(LS_PLAYER_ID_KEY) || "").trim();
  const rid = (localStorage.getItem(LS_RUN_ID_KEY) || "").trim();
  if (!pid || !rid) return;

  joinInFlight = true;
  setJoinEnabled(false);

  socket.emit('resume_player', { player_id: pid, run_id: rid });
}

document.addEventListener("DOMContentLoaded", () => {
  const name = localStorage.getItem(LS_PLAYER_NAME_KEY) || "";
  const input = document.getElementById('name-input');
  if (input && name) input.value = name;

  joinInFlight = false;
  setJoinEnabled(true);
  showSetup();
  focusNameInput(false);

  attemptResumeIfPossible();

  document.getElementById('join-btn')?.addEventListener('click', joinGame);
  document.getElementById('ready-btn')?.addEventListener('click', sendReady);
});

// ---------------- RESUME ACK ----------------

socket.on('resume_ack', (resp) => {
  if (resp && resp.ok) {
    if (resp.player_id) localStorage.setItem(LS_PLAYER_ID_KEY, resp.player_id);
    if (resp.run_id)    localStorage.setItem(LS_RUN_ID_KEY, resp.run_id);
    if (resp.name)      localStorage.setItem(LS_PLAYER_NAME_KEY, resp.name);

    joinInFlight = false;
    setJoinEnabled(true);

    if (resp.ready) showWait();
    else showReady(resp.name);
    return;
  }

  localStorage.removeItem(LS_RUN_ID_KEY);
  joinInFlight = false;
  setJoinEnabled(true);
  showSetup();
  focusNameInput(false);
});

// ---------------- JOIN ----------------

function joinGame() {
  if (joinInFlight) return;

  const name = (document.getElementById('name-input')?.value || "").trim();
  if (!name) {
    alert("Bitte gib einen Namen ein!");
    focusNameInput(false);
    return;
  }

  joinInFlight = true;
  setJoinEnabled(false);

  const existingPlayerId = localStorage.getItem(LS_PLAYER_ID_KEY) || "";
  socket.emit('join_game', { name, player_id: existingPlayerId });
}

socket.on('join_ack', (resp) => {
  joinInFlight = false;
  setJoinEnabled(true);

  if (resp && resp.ok && resp.player_id) {
    localStorage.setItem(LS_PLAYER_ID_KEY, resp.player_id);
    localStorage.setItem(LS_PLAYER_NAME_KEY, resp.name || "");
    if (resp.run_id) localStorage.setItem(LS_RUN_ID_KEY, resp.run_id);
    showReady(resp.name);
    return;
  }

  showSetup();
  focusNameInput(false);

  if (resp?.error === "lobby_closed") {
    alert("Die Lobby ist geschlossen.");
  } else if (resp?.error === "name_taken") {
    alert("Name bereits vergeben.");
  } else {
    alert("Beitritt fehlgeschlagen.");
  }
});

// ---------------- READY ----------------

function sendReady() {
  socket.emit('player_ready');
  showWait();
}

// ---------------- ADMIN EVENTS ----------------

socket.on("admin_player_ready_state", (data) => {
  const ready = !!data?.ready;
  const name  = localStorage.getItem(LS_PLAYER_NAME_KEY) || "";
  if (ready) showWait();
  else showReady(name);
});

socket.on("admin_player_removed", () => {
  localStorage.removeItem(LS_PLAYER_ID_KEY);
  localStorage.removeItem(LS_RUN_ID_KEY);

  joinInFlight = false;
  setJoinEnabled(true);
  showSetup();
  focusNameInput(false);
});
