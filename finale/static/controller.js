// --- FILE: ./finale/static/controller.js ---

const LS_RUN_ID_KEY = "blitzquiz_run_id";
const LS_PLAYER_ID_KEY = "blitzquiz_player_id";

/* ---------- Socket register / reconnect ---------- */
socket.emit('register_controller', {
  player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
  run_id: localStorage.getItem(LS_RUN_ID_KEY) || ""
});

socket.on('connect', () => {
  socket.emit('register_controller', {
    player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
    run_id: localStorage.getItem(LS_RUN_ID_KEY) || ""
  });
});

/* ---------- Screens ---------- */
const titleScreen = document.getElementById("title-screen");
const roundScreen = document.getElementById("round-screen");
const qaScreen    = document.getElementById("qa-screen");

/* ---------- Player header ---------- */
const playerNameEl  = document.getElementById("player-name");
const playerScoreEl = document.getElementById("player-score");

/* ---------- Round ---------- */
const roundLabel  = document.getElementById("round-label");

/* ---------- QA ---------- */
const qText       = document.getElementById("question-text");
const optionsGrid = document.getElementById("options-grid");

/* ---------- Image ---------- */
const qImageWrap  = document.getElementById("question-image-wrap");
const qImageEl    = document.getElementById("question-image");

/* ---------- Timer-Bar ---------- */
const timebarFill = document.getElementById("timebar-fill");

/* ---------- Options ---------- */
const btns = Array.from(document.querySelectorAll(".opt"));

let locked = true;
let isEliminated = false;


/* ---------- WHITE Joker Button / Overlay ---------- */
const whiteBtn = document.getElementById("white-btn");
const jokerOverlay = document.getElementById("joker-overlay");
const jokerIconWhite = document.getElementById("joker-overlay-icon-white");
const jokerIconGold  = document.getElementById("joker-overlay-icon-gold");


/* ---------- NEU: Self + Joker-Counts aus players_ranked ---------- */

function getSelfPlayerId(){
  return (
    localStorage.getItem(LS_PLAYER_ID_KEY) ||
    localStorage.getItem('player_id') ||
    localStorage.getItem('playerId') ||
    sessionStorage.getItem(LS_PLAYER_ID_KEY) ||
    sessionStorage.getItem('player_id') ||
    sessionStorage.getItem('playerId') ||
    null
  );
}

function findMe(playersRanked){
  const selfId = getSelfPlayerId();
  const list = Array.isArray(playersRanked) ? playersRanked : [];
  if (!selfId) return null;
  return list.find(p => String(p.player_id) === String(selfId)) || null;
}

// Aktueller lokaler Stand (nur UI; Backend ist Source of Truth bei nächsten Events)
let selfJokersWhite = null; // number|null
let selfJokersGold  = null; // number|null
let lastGoldUsedForMe = false; // merkt: hat Gold mich in dieser Frage gerettet?

function clampJokers(n){
  const x = Number(n || 0) || 0;
  return Math.max(0, Math.min(2, x));
}

function computeJokerSlots(jokersWhite, jokersGold){
  const w = clampJokers(jokersWhite);
  const g = clampJokers(jokersGold);

  let slot1 = 'none';
  let slot2 = 'none';

  const total = Math.min(2, w + g);

  if (total === 0) {
    slot1 = 'none';
    slot2 = 'none';
  } else if (total === 1) {
    slot1 = 'empty';
    slot2 = (g === 1) ? 'gold' : 'white';
  } else {
    if (g === 2) {
      slot1 = 'gold';
      slot2 = 'gold';
    } else if (w === 2) {
      slot1 = 'white';
      slot2 = 'white';
    } else {
      slot1 = 'white';
      slot2 = 'gold';
    }
  }

  return { slot1, slot2 };
}

function applySelfJokerSlotsFromCounts(w, g){
  const slotsHost = document.getElementById("self-joker-slots");
  if (!slotsHost) return;

  const s1 = slotsHost.querySelector('.ps__jokerSlot[data-slot="1"]');
  const s2 = slotsHost.querySelector('.ps__jokerSlot[data-slot="2"]');
  if (!s1 || !s2) return;

  const { slot1, slot2 } = computeJokerSlots(w, g);
  s1.setAttribute("data-type", slot1);
  s2.setAttribute("data-type", slot2);
}

function updateSelfJokersFromPlayersRanked(playersRanked){
  const me = findMe(playersRanked);
  if (!me) return;

  selfJokersWhite = Math.max(0, Number(me.jokers_white || 0) || 0);
  selfJokersGold  = Math.max(0, Number(me.jokers_gold  || 0) || 0);

  // Joker-Slots oben setzen (wie TV)
  applySelfJokerSlotsFromCounts(selfJokersWhite, selfJokersGold);

  // WHITE Button nur anzeigen, wenn > 0
  if (whiteBtn) {
    whiteBtn.style.display = (selfJokersWhite > 0) ? "" : "none";
  }
}


// Optional: damit White initial nicht kurz aufblitzt
if (whiteBtn) whiteBtn.style.display = "none";


/* ---------- Timer-Bar RAF ---------- */
let timebarRAF = null;

/* ---------- NEU: Answer unveil scheduling ---------- */
let unveilTO = null;

/* ---------- NEU: Server-Clock Sync ---------- */
let clockOffsetMs = 0; // server_now_ms - local_now_ms
function nowSyncedMs() {
  return Date.now() + clockOffsetMs;
}

socket.on('server_time', (data) => {
  const serverNow = data && typeof data.server_now === "number" ? data.server_now : null;
  if (serverNow === null) return;

  // Offset so setzen, dass nowSyncedMs() ~= serverNow
  clockOffsetMs = serverNow - Date.now();
});


/* ---------- NEU: Score-Pop (Backend steuert Timing) ---------- */
let myScorePop = 0;

/* =========================================================
   NEU: Question Rot/Grün + Joker-States
   - setzt .is-correct / .is-wrong / .is-joker-white / .is-joker-gold auf #question-text
   ========================================================= */

function clearQuestionResult(){
  if (!qText) return;
  qText.classList.remove("is-correct", "is-wrong", "is-joker-white", "is-joker-gold");
}

function applyQuestionResult(correctIndex, playerAnswers, opts = {}){
  clearQuestionResult();

  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !playerAnswers) return;

  const myAnswer = playerAnswers[myId];

  // White Joker: Fragefeld soll WEISS werden und Text in Hintergrundfarbe
  if (Number(myAnswer) === 4) {
    qText.classList.add("is-joker-white");
    return;
  }

  // Gold Joker: wenn Gold mich gerettet hat, wird die Frage GOLD (statt rot/gruen)
  const goldUsedForMe = (typeof opts.goldUsedForMe === "boolean")
    ? opts.goldUsedForMe
    : lastGoldUsedForMe;

  if (goldUsedForMe) {
    qText.classList.add("is-joker-gold");
    return;
  }

  // Wenn keine Antwort UND kein Gold: keine Farbe setzen
  if (myAnswer === undefined || myAnswer === null) return;

  const isCorrect = (Number(myAnswer) === Number(correctIndex));
  if (isCorrect) qText.classList.add("is-correct");
  else qText.classList.add("is-wrong");
}

function renderEliminatedScreen(){
  isEliminated = true;

  lockAll();
  hideAnswers();
  stopTimebar();
  clearUnveil();

  // Joker/UI sauber runterfahren
  selfJokersWhite = 0;
  selfJokersGold  = 0;
  applySelfJokerSlotsFromCounts(0, 0);

  if (whiteBtn) whiteBtn.style.display = "none";

  if (jokerOverlay) {
    jokerOverlay.style.display = "none";
    jokerOverlay.classList.remove("is-white", "is-gold");
  }
  if (jokerIconWhite) jokerIconWhite.style.display = "none";
  if (jokerIconGold)  jokerIconGold.style.display  = "none";

  showQA();
  if (qText) {
    qText.textContent = "Ausgeschieden";
    clearQuestionResult();
    qText.classList.add("is-wrong");
  }
}


/* ---------- Screen Switching ---------- */
function showTitle() {
  if (titleScreen) titleScreen.style.display = "flex";
  if (roundScreen) roundScreen.style.display = "none";
  if (qaScreen)    qaScreen.style.display    = "none";
}

function showRound(round) {
  if (roundLabel) roundLabel.textContent = `Frage ${round}`;
  if (titleScreen) titleScreen.style.display = "none";
  if (roundScreen) roundScreen.style.display = "flex";
  if (qaScreen)    qaScreen.style.display    = "none";
}

function showQA() {
  if (titleScreen) titleScreen.style.display = "none";
  if (roundScreen) roundScreen.style.display = "none";
  if (qaScreen)    qaScreen.style.display    = "flex";
}

/* ---------- Helpers ---------- */
function lockAll() {
  locked = true;
  btns.forEach(b => b.classList.add("is-locked"));
  setWhiteEnabled(false);
}


function unlockAll() {
  locked = false;
  btns.forEach(b => b.classList.remove("is-locked"));
  setWhiteEnabled(true);
}

function hideAnswers() {
  if (optionsGrid) optionsGrid.classList.add("is-invisible");
}

function showAnswers() {
  if (optionsGrid) optionsGrid.classList.remove("is-invisible");
}

/* NEU: nur enthüllen (sichtbar machen), Lock/Unlock kommt ausschließlich über open_answers/close_answers */
function unveilAnswersOnly() {
  showAnswers();
  // NICHT lockAll(): sonst kann ein später feuender Unveil-Timeout die Buttons wieder sperren
}

function setWhiteEnabled(enabled) {
  if (!whiteBtn) return;
  whiteBtn.classList.toggle("is-locked", !enabled);
}


function resetAnswerVisuals() {
  // A–D zurücksetzen
  btns.forEach(b => {
    b.classList.remove("is-dim", "is-selected", "is-correct", "is-wrong", "is-faded");
  });

// White Button visuell zurücksetzen (SICHTBARKEIT NICHT HIER STEUERN)
if (whiteBtn) {
  whiteBtn.classList.remove("is-dim");
}


  // Joker Overlay komplett zurücksetzen
  if (jokerOverlay) {
    jokerOverlay.style.display = "none";
    jokerOverlay.classList.remove("is-white", "is-gold");
  }

  if (jokerIconWhite) jokerIconWhite.style.display = "none";
  if (jokerIconGold)  jokerIconGold.style.display  = "none";
}



function lockAfterAnswer(selectedIdx) {
  locked = true;

  // A–D locken + dimmen (außer Selected)
  btns.forEach((b, i) => {
    b.classList.add("is-locked");
    if (i === selectedIdx) {
      b.classList.add("is-selected");
      b.classList.remove("is-dim");
    } else {
      b.classList.add("is-dim");
    }
  });

  // NEU: Wenn White sichtbar ist, soll er beim Klick auf A–D auch gedimmt werden (0.45 via .is-dim)
  if (whiteBtn && whiteBtn.style.display !== "none") {
    whiteBtn.classList.add("is-dim");
  }
}


/* ---------- Image ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/finale/media/dummy.png';
  const file = (imageFile || '').trim();

  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  if (!file) return;

  if (qImageWrap) qImageWrap.classList.remove('is-hidden');

  const isAbsolute =
    file.startsWith('http://') ||
    file.startsWith('https://') ||
    file.startsWith('/');

  if (qImageEl) {
    qImageEl.src = isAbsolute ? file : `/finale/media/images/${file}`;
    qImageEl.onerror = () => {
      qImageEl.onerror = null;
      qImageEl.src = fallback;
    };
  }
}

/* ---------- Score Rendering (NEU) ---------- */
function clearScorePopInline() {
  myScorePop = 0;
  if (playerScoreEl) {
    const current = (playerScoreEl.textContent || "").trim();
    if (current) playerScoreEl.textContent = current;
  }
}

function renderScoreWithPop(scoreValue, popValue) {
  if (!playerScoreEl) return;

  const score = (scoreValue ?? "—");
  const pop = Number(popValue || 0);

  if (pop > 0) {
    playerScoreEl.innerHTML =
      `<span class="psc__scorePopInline" style="display:inline;">+${pop}</span>` +
      `<span class="ps__scoreText psc__scoreValue">${score}</span>`;
  } else {
    playerScoreEl.innerHTML =
      `<span class="psc__scorePopInline" style="display:none;">+0</span>` +
      `<span class="ps__scoreText psc__scoreValue">${score}</span>`;
  }
}


/* ---------- Player Header Update ---------- */
function updatePlayerHeader(playersRanked) {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !playersRanked) return;

  const me = playersRanked.find(p => String(p.player_id) === String(myId));
  if (!me) return;

  // Name wie gehabt
  if (playerNameEl) {
    playerNameEl.textContent = me.name || "—";
  }

  // SCORE-BOX: IMMER nur aktueller Score, kein Pop
  if (playerScoreEl) {
    playerScoreEl.textContent = (me.score ?? "—");
  }
}


/* ---------- Timer-Bar ---------- */
function parseStartedAtToMs(startedAt) {
  if (startedAt === undefined || startedAt === null) return null;

  if (typeof startedAt === "number") {
    if (startedAt > 1e12) return startedAt;          // ms
    if (startedAt > 1e9)  return startedAt * 1000;   // sec -> ms
    return startedAt;
  }

  if (typeof startedAt === "string") {
    const t = Date.parse(startedAt);
    return Number.isFinite(t) ? t : null;
  }

  return null;
}

function stopTimebar() {
  if (timebarRAF) {
    cancelAnimationFrame(timebarRAF);
    timebarRAF = null;
  }
  if (timebarFill) timebarFill.style.width = "0%";
}

function startTimebar(seconds, startedAt /* optional */) {
  if (!timebarFill) return;

  stopTimebar();

  const durMs = Math.max(0.001, Number(seconds || 1)) * 1000;
  const startedAtMs = parseStartedAtToMs(startedAt);

  if (startedAtMs !== null) {
    const endAtMs = startedAtMs + durMs;

    const tick = () => {
      const nowMs = nowSyncedMs();
      const elapsed = nowMs - startedAtMs;
      const pct = Math.min(100, Math.max(0, (elapsed / durMs) * 100));
      timebarFill.style.width = `${pct}%`;

      if (nowMs < endAtMs) {
        timebarRAF = requestAnimationFrame(tick);
      } else {
        stopTimebar();
      }
    };

    timebarRAF = requestAnimationFrame(tick);
    return;
  }


  const start = performance.now();

  const tick = (now) => {
    const elapsed = now - start;
    const pct = Math.min(100, (elapsed / durMs) * 100);
    timebarFill.style.width = `${pct}%`;
    if (pct < 100) {
      timebarRAF = requestAnimationFrame(tick);
    } else {
      stopTimebar();
    }
  };

  timebarRAF = requestAnimationFrame(tick);
}

/* ---------- NEU: Unveil by absolute timestamp ---------- */
function clearUnveil() {
  if (unveilTO) {
    clearTimeout(unveilTO);
    unveilTO = null;
  }
}

function scheduleAnswersUnveilAt(isoTs) {
  clearUnveil();

  const tMs = parseStartedAtToMs(isoTs);
  if (tMs === null) return;

  const delay = tMs - nowSyncedMs();
  if (delay <= 0) {
    unveilAnswersOnly();
    return;
  }

  unveilTO = setTimeout(() => {
    unveilTO = null;
    unveilAnswersOnly();
  }, delay);
}


/* ---------- Reconnect ---------- */
document.addEventListener("DOMContentLoaded", () => {
  const playerId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const runId = localStorage.getItem(LS_RUN_ID_KEY);
  if (playerId) {
    socket.emit('resume_player', { player_id: playerId, run_id: runId || "" });
  }

  const v = document.getElementById('ps-controller-video');
  if (v) v.play().catch(()=>{});
});

/* ---------- Init ---------- */
showTitle();
hideAnswers();
lockAll();
stopTimebar();
clearUnveil();
clearScorePopInline();
clearQuestionResult();

/* ---------- Socket Events ---------- */

socket.on("play_round_video", (data) => {
  if (isEliminated) return;

  showRound(Number(data.round || 1));
  resetAnswerVisuals();
  hideAnswers();
  lockAll();
  stopTimebar();
  clearUnveil();
  clearScorePopInline();
  clearQuestionResult();
  lastGoldUsedForMe = false;
});


socket.on("show_question", (data) => {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);

  // Wenn ich wieder in players_ranked auftauche (neuer Run / Reset): elim-Flag zurücksetzen
  if (myId && Array.isArray(data.players_ranked)) {
    const amActive = data.players_ranked.some(p => String(p.player_id) === String(myId));
    if (amActive) isEliminated = false;
  }

  if (isEliminated) return;

  showQA();

  if (qText) qText.textContent = data.text || "";
  setQuestionImage(data.image);

  (data.options || []).forEach((t, i) => {
    if (btns[i]) btns[i].textContent = t;
  });

  // Header setzen (ohne Pop)
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });

  // Jokerstände für mich ziehen + WHITE sichtbar/unsichtbar
  updateSelfJokersFromPlayersRanked(data.players_ranked);

  resetAnswerVisuals();
  hideAnswers();
  lockAll();
  stopTimebar();
  clearUnveil();
  clearScorePopInline();
  clearQuestionResult();

  // Wenn Backend absolute Zeit liefert, Answers schon vor open_answers "geplant" enthüllen
  if (data && (data.answers_unveil_at || data.answersUnveilAt)) {
    scheduleAnswersUnveilAt(data.answers_unveil_at || data.answersUnveilAt);
  }
});


socket.on("open_answers", (data) => {
  if (isEliminated) return;

  resetAnswerVisuals();
  clearUnveil(); // <- WICHTIG: geplantes Unveil darf später nicht mehr re-locken

  // Definitiver Start für Interaktion (unlock) + Timer
  showAnswers();
  unlockAll();
  clearQuestionResult();
  lastGoldUsedForMe = false;

  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);

  // Bei Reconnect kommt duration=remaining, aber started_at ist der originale Start.
  // Darum IMMER mit total_duration rechnen.
  const dur = Number((data && (data.total_duration ?? data.totalDuration ?? data.duration)) || 15);

  startTimebar(dur, startedAt);
});



socket.on("close_answers", () => {
  lockAll();
  stopTimebar();
});

socket.on("reveal_player_answers", () => {
  stopTimebar();
});

socket.on("unveil_correct", (data) => {
  // Controller: in dieser Phase noch KEIN grün/rot.
  // Wir frieren nur ein (Lock + Timer stop).
  lockAll();
  stopTimebar();

  // WICHTIG: keine Klassen an den Buttons setzen/ändern.
  // So bleibt die optische Auflösung exklusiv in show_resolution.
});



socket.on("show_resolution", (data) => {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);

  // Wenn Backend sagt: ich bin eliminiert -> sofort Eliminated-Screen
  const eliminatedList = (data && data.finale_meta && Array.isArray(data.finale_meta.eliminated))
    ? data.finale_meta.eliminated
    : [];

  const iAmEliminated = !!(myId && eliminatedList.some(pid => String(pid) === String(myId)));
  if (iAmEliminated) {
    renderEliminatedScreen();
    return;
  }

  if (isEliminated) return;

  lockAll();
  stopTimebar();

  // WICHTIG: für Jokerstände/Score NACH Sudden-Death Apply
  const rankedNext = (data && Array.isArray(data.players_ranked_next))
    ? data.players_ranked_next
    : data.players_ranked;

  updateSelfJokersFromPlayersRanked(rankedNext);

  const correctIdx = Number(data.correct_index);
  const myAnswer = (data.player_answers && myId) ? data.player_answers[myId] : null;

  // Overlay erstmal zurücksetzen (damit Reconnect sauber ist)
  if (jokerOverlay) {
    jokerOverlay.style.display = "none";
    jokerOverlay.classList.remove("is-white", "is-gold");
  }
  if (jokerIconWhite) jokerIconWhite.style.display = "none";
  if (jokerIconGold)  jokerIconGold.style.display  = "none";

  // GOLD: wurde ich in dieser Frage durch Gold gerettet?
  const goldUsedList = (data && data.finale_meta && Array.isArray(data.finale_meta.gold_used))
    ? data.finale_meta.gold_used
    : [];

  lastGoldUsedForMe = !!(myId && goldUsedList.some(pid => String(pid) === String(myId)));

  // WHITE: wurde White genutzt (für Reconnect-Fall)
  const whiteUsedList = (data && data.finale_meta && Array.isArray(data.finale_meta.white_used))
    ? data.finale_meta.white_used
    : [];

  const whiteUsedForMe = !!(
    myId && (Number(myAnswer) === 4 || whiteUsedList.some(pid => String(pid) === String(myId)))
  );

  // Overlay anzeigen: White hat Vorrang vor Gold
  if (whiteUsedForMe && jokerOverlay) {
    jokerOverlay.style.display = "flex";
    jokerOverlay.classList.remove("is-gold");
    jokerOverlay.classList.add("is-white");
    if (jokerIconWhite) jokerIconWhite.style.display = "block";
    if (jokerIconGold)  jokerIconGold.style.display  = "none";
  } else if (lastGoldUsedForMe && jokerOverlay) {
    jokerOverlay.style.display = "flex";
    jokerOverlay.classList.remove("is-white");
    jokerOverlay.classList.add("is-gold");
    if (jokerIconGold)  jokerIconGold.style.display  = "block";
    if (jokerIconWhite) jokerIconWhite.style.display = "none";
  }

  btns.forEach((b, i) => {
    b.classList.remove("is-selected", "is-dim", "is-correct", "is-wrong", "is-faded");

    if (i === correctIdx) {
      b.classList.add("is-correct");
    } else if (myAnswer !== null && Number(myAnswer) !== 4 && i === Number(myAnswer)) {
      b.classList.add("is-wrong");
    } else {
      b.classList.add("is-faded");
    }
  });

  applyQuestionResult(correctIdx, data.player_answers, { goldUsedForMe: lastGoldUsedForMe });
});

socket.on("finale_eliminated", (data) => {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const eliminated = (data && Array.isArray(data.eliminated)) ? data.eliminated : [];

  const iAmEliminated = !!(myId && eliminated.some(pid => String(pid) === String(myId)));
  if (!iAmEliminated) return;

  renderEliminatedScreen();
});



function isPopPayload(data) {
  const phase = (data && (data.phase || data.mode || data.step) || "").toString().toLowerCase();
  if (phase === "pop" || phase === "points_pop" || phase === "reveal_points") return true;
  if (phase === "show_points") return true;
  if (data && data.show_pop === true) return true;
  return false;
}

socket.on("show_scoring_pop", (data) => {
  updatePlayerHeader(data.players_ranked, data.gained || {}, { forcePop: true });
  stopTimebar();
  applyQuestionResult(Number(data.correct_index), data.player_answers, { goldUsedForMe: lastGoldUsedForMe });

});

socket.on("show_scoring_update", (data) => {
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
  // clearQuestionResult() entfernt, damit Farbe bleibt
});

socket.on("show_scoring", (data) => {
  updateSelfJokersFromPlayersRanked(data.players_ranked);
  if (isPopPayload(data)) {
    updatePlayerHeader(data.players_ranked, data.gained || {}, { forcePop: true });
  } else {
    updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  }
  stopTimebar();

  if (data && data.correct_index !== undefined && data.player_answers) {
    applyQuestionResult(Number(data.correct_index), data.player_answers, { goldUsedForMe: lastGoldUsedForMe });
  }
  // clearQuestionResult() im else-Pfad entfernt
});

socket.on("apply_scoring_update", (data) => {
  updateSelfJokersFromPlayersRanked(data.players_ranked);
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
  // clearQuestionResult() entfernt
});

/* ---------- Input ---------- */
btns.forEach(btn => {
  btn.addEventListener("pointerup", () => {
    if (locked) return;
    const idx = Number(btn.dataset.index);
    lockAfterAnswer(idx);

    socket.emit("module_event", {
  action: "submit_answer",
  payload: { choice: idx }
});

  });
});

/* ---------- WHITE Joker Input ---------- */
if (whiteBtn) {
  whiteBtn.addEventListener("pointerup", () => {
    if (locked) return;

    if (typeof selfJokersWhite === "number" && selfJokersWhite <= 0) return;

    locked = true;

    // A–D locken + dimmen
    btns.forEach(b => {
      b.classList.add("is-locked");
      b.classList.add("is-dim");
    });

    // WHITE BUTTON sofort ausblenden
    whiteBtn.style.display = "none";

    // JOKER OVERLAY (WHITE) aktivieren
    if (jokerOverlay) {
      jokerOverlay.style.display = "flex";
      jokerOverlay.classList.add("is-white");
    }

    if (jokerIconWhite) jokerIconWhite.style.display = "block";
    if (jokerIconGold)  jokerIconGold.style.display  = "none";

    socket.emit("module_event", {
      action: "submit_answer",
      payload: { choice: 4 }
    });
  });
}

