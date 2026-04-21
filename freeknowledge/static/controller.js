// --- FILE: ./freeknowledge/static/controller.js ---

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
const qText = document.getElementById("question-text");

/* ---------- Freitext ---------- */
const answerForm   = document.getElementById("answer-form");
const answerInput  = document.getElementById("answer-input");
const answerSubmit = document.getElementById("answer-submit");
const answerHint   = document.getElementById("answer-hint");

let locked = true;
let hasSubmitted = false;

/* ---------- Image ---------- */
const qImageWrap  = document.getElementById("question-image-wrap");
const qImageEl    = document.getElementById("question-image");

/* ---------- Timer-Bar ---------- */
const timebarFill = document.getElementById("timebar-fill");

/* ---------- Timer-Bar RAF ---------- */
let timebarRAF = null;

/* ---------- Server-Clock Sync ---------- */
let clockOffsetMs = 0; // server_now_ms - local_now_ms
function nowSyncedMs() {
  return Date.now() + clockOffsetMs;
}

socket.on('server_time', (data) => {
  const serverNow = data && typeof data.server_now === "number" ? data.server_now : null;
  if (serverNow === null) return;
  clockOffsetMs = serverNow - Date.now();
});

/* ---------- Score-Pop (Backend steuert Timing) ---------- */
let myScorePop = 0;

/* =========================================================
   Question Rot/Grün wie TV (für den jeweiligen Spieler)
   - setzt .is-correct / .is-wrong auf #question-text
   ========================================================= */

function clearQuestionResult(){
  if (!qText) return;
  qText.classList.remove("is-correct", "is-wrong");
}

function applyQuestionResult(isCorrect){
  clearQuestionResult();
  if (!qText) return;
  if (isCorrect === true) qText.classList.add("is-correct");
  if (isCorrect === false) qText.classList.add("is-wrong");
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

/* ---------- Helpers (Lock/Unlock) ---------- */
function lockAll() {
  locked = true;
  hasSubmitted = true;

  if (answerInput)  answerInput.disabled = true;
  if (answerSubmit) answerSubmit.disabled = true;

  if (answerInput)  answerInput.classList.add("is-locked");
  if (answerSubmit) answerSubmit.classList.add("is-locked");
}

function unlockAll() {
  locked = false;
  hasSubmitted = false;

  if (answerInput)  answerInput.disabled = false;
  if (answerSubmit) answerSubmit.disabled = false;

  if (answerInput)  answerInput.classList.remove("is-locked");
  if (answerSubmit) answerSubmit.classList.remove("is-locked");
}

function clearAnswerInput() {
  if (answerInput) answerInput.value = "";
  if (answerHint) {
    answerHint.classList.add("is-hidden");
    answerHint.setAttribute("aria-hidden", "true");
  }
}

function showAnswerHint() {
  if (!answerHint) return;
  answerHint.classList.remove("is-hidden");
  answerHint.setAttribute("aria-hidden", "false");
}

/* Eingabe-Normalisierung */
function normalizeAnswerInput(raw) {
  return String(raw ?? "").trim();
}

function submitAnswer() {
  if (locked || hasSubmitted) return;

  const raw = answerInput ? answerInput.value : "";
  const text = normalizeAnswerInput(raw);

  if (!text) {
    showAnswerHint();
    return;
  }

  lockAll();

  socket.emit("module_event", {
    action: "submit_answer",
    payload: { text }
  });
}

/* ---------- Image ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/freeknowledge/media/dummy.png';
  const file = (imageFile || '').trim();

  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  if (!file) return;

  if (qImageWrap) qImageWrap.classList.remove('is-hidden');

  const isAbsolute =
    file.startsWith('http://') ||
    file.startsWith('https://') ||
    file.startsWith('/');

  if (qImageEl) {
    qImageEl.src = isAbsolute ? file : `/freeknowledge/media/images/${file}`;
    qImageEl.onerror = () => {
      qImageEl.onerror = null;
      qImageEl.src = fallback;
    };
  }
}

/* ---------- Score Rendering ---------- */
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

      if (nowMs < endAtMs) timebarRAF = requestAnimationFrame(tick);
      else stopTimebar();
    };

    timebarRAF = requestAnimationFrame(tick);
    return;
  }

  const start = performance.now();
  const tick = (now) => {
    const elapsed = now - start;
    const pct = Math.min(100, (elapsed / durMs) * 100);
    timebarFill.style.width = `${pct}%`;
    if (pct < 100) timebarRAF = requestAnimationFrame(tick);
    else stopTimebar();
  };

  timebarRAF = requestAnimationFrame(tick);
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
lockAll();
stopTimebar();
clearScorePopInline();
clearQuestionResult();
clearAnswerInput();

/* ---------- Socket Events ---------- */

socket.on("play_round_video", (data) => {
  showRound(Number(data.round || 1));
  lockAll();
  stopTimebar();
  clearScorePopInline();
  clearQuestionResult();
  clearAnswerInput();
});

socket.on("show_question", (data) => {
  showQA();

  if (qText) qText.textContent = data.text || "";
  setQuestionImage(data.image);

  // Header setzen (ohne Pop)
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });

  lockAll();
  stopTimebar();
  clearScorePopInline();
  clearQuestionResult();
  clearAnswerInput();
});

socket.on("open_answers", (data) => {
  // Start für Interaktion
  unlockAll();
  clearQuestionResult();

  // Fokus + Tastatur
  if (answerInput) {
    answerInput.focus();
    answerInput.select();
  }

  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);
  const dur = Number((data && (data.total_duration ?? data.totalDuration ?? data.duration)) || 15);

  startTimebar(dur, startedAt);
});

socket.on("close_answers", () => {
  lockAll();
  stopTimebar();
});

socket.on("reveal_player_answers", (data) => {
  stopTimebar();

  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !answerInput) return;

  const playerAnswers = data && data.player_answers ? data.player_answers : {};
  const myAnswer = playerAnswers[myId];

  if (typeof myAnswer === "string") {
    answerInput.value = myAnswer;
    return;
  }

  if (myAnswer && typeof myAnswer === "object") {
    const txt = myAnswer.text ?? myAnswer.raw ?? "";
    answerInput.value = String(txt || "");
  }
});

socket.on("unveil_correct", () => {
  lockAll();
  stopTimebar();
});

socket.on("show_resolution", (data) => {
  lockAll();
  stopTimebar();

  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  let isCorrect = null;

  // 1) Details-Map bevorzugt
  const details = data && data.details ? data.details : null;
  if (details && myId) {
    const mine = details[myId];
    if (mine && typeof mine.accepted === "boolean") {
      isCorrect = !!mine.accepted;
    }

    if (mine && answerInput) {
      const raw =
        mine.raw_answer ??
        mine.rawAnswer ??
        mine.answer ??
        mine.player_answer ??
        mine.playerAnswer;

      if (raw !== undefined && raw !== null) {
        answerInput.value = String(raw);
      }
    }
  }

  // 2) Fallback: simple compare
  if (isCorrect === null && myId && data && data.player_answers) {
    const myAns = data.player_answers[myId];
    const correct = (data.correct ?? "").toString().trim();
    const myText =
      typeof myAns === "object" && myAns !== null
        ? String(myAns.text ?? myAns.raw ?? "").trim()
        : String(myAns ?? "").trim();

    if (myText && correct) {
      isCorrect = (myText === correct);
    }
  }

  applyQuestionResult(isCorrect);
});

function isPopPayload(data) {
  const phase = (data && (data.phase || data.mode || data.step) || "").toString().toLowerCase();
  if (phase === "pop" || phase === "points_pop" || phase === "reveal_points") return true;
  if (phase === "show_points") return true;
  if (data && data.show_pop === true) return true;
  return false;
}

socket.on("show_scoring", (data) => {
  if (isPopPayload(data)) {
    updatePlayerHeader(data.players_ranked, data.gained || {}, { forcePop: true });
  } else {
    updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  }
  stopTimebar();
});

socket.on("apply_scoring_update", (data) => {
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
});

/* ---------- Input (Freetext) ---------- */
if (answerForm) {
  answerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    submitAnswer();
  });
}

if (answerInput) {
  answerInput.addEventListener("input", () => {
    if (answerHint) {
      answerHint.classList.add("is-hidden");
      answerHint.setAttribute("aria-hidden", "true");
    }
  });

  answerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitAnswer();
    }
  });
}

if (answerSubmit) {
  answerSubmit.addEventListener("pointerup", (e) => {
    e.preventDefault();
    submitAnswer();
  });
}