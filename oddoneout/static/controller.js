// --- FILE: ./oddoneout/static/controller.js ---

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
   NEU: Question Rot/Grün wie TV (für den jeweiligen Spieler)
   - setzt .is-correct / .is-wrong auf #question-text
   ========================================================= */

function clearQuestionResult(){
  if (!qText) return;
  qText.classList.remove("is-correct", "is-wrong");
}

function applyQuestionResult(correctIndex, playerAnswers){
  clearQuestionResult();

  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !playerAnswers) return;

  const myAnswer = playerAnswers[myId];
  if (myAnswer === undefined || myAnswer === null) return;

  if (Number(myAnswer) === Number(correctIndex)) {
    qText.classList.add("is-correct");
  } else {
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
}

function unlockAll() {
  locked = false;
  btns.forEach(b => b.classList.remove("is-locked"));
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


function resetAnswerVisuals() {
  btns.forEach(b => {
    b.classList.remove("is-dim", "is-selected", "is-correct", "is-wrong", "is-faded");
  });
}

function lockAfterAnswer(selectedIdx) {
  locked = true;
  btns.forEach((b, i) => {
    b.classList.add("is-locked");
    if (i === selectedIdx) {
      b.classList.add("is-selected");
      b.classList.remove("is-dim");
    } else {
      b.classList.add("is-dim");
    }
  });
}

/* ---------- Image ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/oddoneout/media/dummy.png';
  const file = (imageFile || '').trim();

  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  if (!file) return;

  if (qImageWrap) qImageWrap.classList.remove('is-hidden');

  const isAbsolute =
    file.startsWith('http://') ||
    file.startsWith('https://') ||
    file.startsWith('/');

  if (qImageEl) {
    qImageEl.src = isAbsolute ? file : `/oddoneout/media/images/${file}`;
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
      `<span class="psc__scorePopInline">+${pop}</span>` +
      `<span class="psc__scoreValue">${score}</span>`;
  } else {
    playerScoreEl.textContent = `${score}`;
  }
}

/* ---------- Player Header Update ---------- */
function updatePlayerHeader(playersRanked, gainedMap, opts = {}) {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !playersRanked) return;

  const me = playersRanked.find(p => p.player_id === myId);
  if (!me) return;

  if (playerNameEl) playerNameEl.textContent = me.name || "—";

  const score = (me.score ?? "—");

  if (opts.forceClear) {
    myScorePop = 0;
    renderScoreWithPop(score, 0);
    return;
  }

  const gained = gainedMap && Object.prototype.hasOwnProperty.call(gainedMap, myId)
    ? Number(gainedMap[myId] || 0)
    : 0;

  if (opts.forcePop) {
    myScorePop = gained > 0 ? gained : myScorePop;
    renderScoreWithPop(score, myScorePop);
    return;
  }

  if (gained > 0) {
    myScorePop = gained;
    renderScoreWithPop(score, myScorePop);
  } else {
    myScorePop = 0;
    renderScoreWithPop(score, 0);
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
  showRound(Number(data.round || 1));
  resetAnswerVisuals();
  hideAnswers();
  lockAll();
  stopTimebar();
  clearUnveil();
  clearScorePopInline();
  clearQuestionResult();
});

socket.on("show_question", (data) => {
  showQA();

  if (qText) qText.textContent = data.text || "";
  setQuestionImage(data.image);

  (data.options || []).forEach((t, i) => {
    if (btns[i]) btns[i].textContent = t;
  });

  // Header setzen (ohne Pop)
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });

  resetAnswerVisuals();
  hideAnswers();
  lockAll();
  stopTimebar();
  clearUnveil();
  clearScorePopInline();
  clearQuestionResult();

  // NEU: Wenn Backend absolute Zeit liefert, Answers schon vor open_answers "geplant" enthüllen
  if (data && (data.answers_unveil_at || data.answersUnveilAt)) {
    scheduleAnswersUnveilAt(data.answers_unveil_at || data.answersUnveilAt);
  }
});

socket.on("open_answers", (data) => {
  resetAnswerVisuals();
  clearUnveil(); // <- WICHTIG: geplantes Unveil darf später nicht mehr re-locken

  // Definitiver Start für Interaktion (unlock) + Timer
  showAnswers();
  unlockAll();
  clearQuestionResult();


  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);

  // WICHTIG:
  // Bei Reconnect kommt duration=remaining, aber started_at ist der originale Start.
  // Darum IMMER mit total_duration rechnen (damit der Fortschritt korrekt ist).
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
  lockAll();
  stopTimebar();

  const correctIdx = Number(data.correct_index);
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const myAnswer = (data.player_answers && myId) ? data.player_answers[myId] : null;

  btns.forEach((b, i) => {
    b.classList.remove("is-selected", "is-dim", "is-correct", "is-wrong", "is-faded");


    if (i === correctIdx) {
      b.classList.add("is-correct");
    } else if (myAnswer !== null && i === Number(myAnswer)) {
      b.classList.add("is-wrong");
    } else {
      b.classList.add("is-faded");
    }
  });

  applyQuestionResult(correctIdx, data.player_answers);
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
  applyQuestionResult(Number(data.correct_index), data.player_answers);
});

socket.on("show_scoring_update", (data) => {
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
  // clearQuestionResult() entfernt, damit Farbe bleibt
});

socket.on("show_scoring", (data) => {
  if (isPopPayload(data)) {
    updatePlayerHeader(data.players_ranked, data.gained || {}, { forcePop: true });
  } else {
    updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  }
  stopTimebar();

  if (data && data.correct_index !== undefined && data.player_answers) {
    applyQuestionResult(Number(data.correct_index), data.player_answers);
  }
  // clearQuestionResult() im else-Pfad entfernt
});

socket.on("apply_scoring_update", (data) => {
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
      payload: { index: idx }
    });
  });
});
