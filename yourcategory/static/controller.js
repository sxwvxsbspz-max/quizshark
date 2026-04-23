// === YOURCATEGORY CONTROLLER JS ===

const LS_RUN_ID_KEY    = "blitzquiz_run_id";
const LS_PLAYER_ID_KEY = "blitzquiz_player_id";

/* ---------- Socket register / reconnect ---------- */
socket.emit('register_controller', {
  player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
  run_id:    localStorage.getItem(LS_RUN_ID_KEY)    || "",
});

socket.on('connect', () => {
  socket.emit('register_controller', {
    player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
    run_id:    localStorage.getItem(LS_RUN_ID_KEY)    || "",
  });
});

/* ---------- Screens ---------- */
const titleScreen  = document.getElementById("title-screen");
const ycInputScreen = document.getElementById("yc-input-screen");
const roundScreen  = document.getElementById("round-screen");
const qaScreen     = document.getElementById("qa-screen");

function showScreen(el) {
  [titleScreen, ycInputScreen, roundScreen, qaScreen].forEach(s => {
    if (s) s.style.display = (s === el) ? (el === qaScreen || el === ycInputScreen ? 'flex' : 'flex') : 'none';
  });
}

/* ---------- Server clock sync ---------- */
let clockOffsetMs = 0;
function nowSyncedMs() { return Date.now() + clockOffsetMs; }

socket.on('server_time', data => {
  const sn = data && typeof data.server_now === 'number' ? data.server_now : null;
  if (sn !== null) clockOffsetMs = sn - Date.now();
});

/* ---------- Category Input references ---------- */
const inputPlayerName  = document.getElementById("input-player-name");
const inputPlayerScore = document.getElementById("input-player-score");
const inputTimebarFill = document.getElementById("input-timebar-fill");
const categoryForm     = document.getElementById("category-form");
const categoryInput    = document.getElementById("category-input");
const categorySubmit   = document.getElementById("category-submit");
const categoryHint     = document.getElementById("category-hint");
const suggestionBtns   = document.getElementById("suggestion-buttons");

let categoryLocked    = false;
let categorySubmitted = false;
let currentOptions    = [];   // [{id, category}, ...]

/* ---------- MC QA references ---------- */
const playerNameEl  = document.getElementById("player-name");
const playerScoreEl = document.getElementById("player-score");
const roundLabel    = document.getElementById("round-label");
const qText         = document.getElementById("question-text");
const optionsGrid   = document.getElementById("options-grid");
const qImageWrap    = document.getElementById("question-image-wrap");
const qImageEl      = document.getElementById("question-image");
const timebarFill   = document.getElementById("timebar-fill");

const btns = Array.from(document.querySelectorAll(".opt"));
let locked = true;

/* ---------- Timer-Bar RAF ---------- */
let timebarRAF     = null;
let inputTimerRAF  = null;
let unveilTO       = null;
let myScorePop     = 0;

/* ---------- parseMs ---------- */
function parseMs(val) {
  if (val === null || val === undefined) return null;
  if (typeof val === 'number') {
    if (val > 1e12) return val;
    if (val > 1e9)  return val * 1000;
    return val;
  }
  if (typeof val === 'string') {
    const t = Date.parse(val);
    return Number.isFinite(t) ? t : null;
  }
  return null;
}

/* ---------- Input Timer Bar ---------- */
function stopInputTimebar() {
  if (inputTimerRAF) { cancelAnimationFrame(inputTimerRAF); inputTimerRAF = null; }
  if (inputTimebarFill) inputTimebarFill.style.width = '0%';
}

function startInputTimebar(endsAt, duration) {
  stopInputTimebar();
  if (!inputTimebarFill) return;
  const endMs   = parseMs(endsAt);
  const startMs = endMs ? endMs - duration * 1000 : null;
  if (!endMs || !startMs) return;

  const tick = () => {
    const now = nowSyncedMs();
    const pct = Math.min(100, Math.max(0, ((now - startMs) / (duration * 1000)) * 100));
    inputTimebarFill.style.width = pct + '%';
    if (now < endMs) inputTimerRAF = requestAnimationFrame(tick);
    else stopInputTimebar();
  };
  inputTimerRAF = requestAnimationFrame(tick);
}

/* ---------- MC Timer Bar ---------- */
function stopTimebar() {
  if (timebarRAF) { cancelAnimationFrame(timebarRAF); timebarRAF = null; }
  if (timebarFill) timebarFill.style.width = '0%';
}

function startTimebar(seconds, startedAt) {
  if (!timebarFill) return;
  stopTimebar();
  const durMs = Math.max(0.001, Number(seconds || 1)) * 1000;
  const startMs = parseMs(startedAt);

  if (startMs !== null) {
    const endMs = startMs + durMs;
    const tick = () => {
      const now = nowSyncedMs();
      const pct = Math.min(100, Math.max(0, ((now - startMs) / durMs) * 100));
      timebarFill.style.width = pct + '%';
      if (now < endMs) timebarRAF = requestAnimationFrame(tick);
      else stopTimebar();
    };
    timebarRAF = requestAnimationFrame(tick);
    return;
  }

  const start = performance.now();
  const tick = now => {
    const pct = Math.min(100, ((now - start) / durMs) * 100);
    timebarFill.style.width = pct + '%';
    if (pct < 100) timebarRAF = requestAnimationFrame(tick);
    else stopTimebar();
  };
  timebarRAF = requestAnimationFrame(tick);
}

/* ---------- Unveil scheduling ---------- */
function clearUnveil() {
  if (unveilTO) { clearTimeout(unveilTO); unveilTO = null; }
}

function scheduleAnswersUnveilAt(isoTs) {
  clearUnveil();
  const tMs = parseMs(isoTs);
  if (tMs === null) return;
  const delay = tMs - nowSyncedMs();
  if (delay <= 0) { showAnswers(); return; }
  unveilTO = setTimeout(() => { unveilTO = null; showAnswers(); }, delay);
}

/* ---------- MC Answer Helpers ---------- */
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

function resetAnswerVisuals() {
  btns.forEach(b =>
    b.classList.remove("is-dim","is-selected","is-correct","is-wrong","is-faded"));
}

function lockAfterAnswer(idx) {
  locked = true;
  btns.forEach((b, i) => {
    b.classList.add("is-locked");
    if (i === idx) { b.classList.add("is-selected"); b.classList.remove("is-dim"); }
    else           { b.classList.add("is-dim"); }
  });
}

function clearQuestionResult() {
  if (qText) qText.classList.remove("is-correct","is-wrong");
}

function applyQuestionResult(correctIndex, playerAnswers) {
  clearQuestionResult();
  const myId  = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !playerAnswers) return;
  const myAns = playerAnswers[myId];
  if (myAns === undefined || myAns === null) return;
  if (Number(myAns) === Number(correctIndex)) qText.classList.add("is-correct");
  else qText.classList.add("is-wrong");
}

/* ---------- Score Rendering ---------- */
function clearScorePopInline() {
  myScorePop = 0;
  if (playerScoreEl) playerScoreEl.textContent = (playerScoreEl.textContent || "").trim();
}

function renderScoreWithPop(score, pop) {
  if (!playerScoreEl) return;
  if (Number(pop) > 0) {
    playerScoreEl.innerHTML =
      `<span class="psc__scorePopInline">+${pop}</span>` +
      `<span class="psc__scoreValue">${score ?? "—"}</span>`;
  } else {
    playerScoreEl.textContent = `${score ?? "—"}`;
  }
}

function updatePlayerHeader(ranked, gainedMap, opts = {}) {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !ranked) return;
  const me = ranked.find(p => p.player_id === myId);
  if (!me) return;

  if (playerNameEl) playerNameEl.textContent = me.name || "—";
  const score = me.score ?? "—";

  if (opts.forceClear) { myScorePop = 0; renderScoreWithPop(score, 0); return; }
  const gained = gainedMap && Object.prototype.hasOwnProperty.call(gainedMap, myId)
    ? Number(gainedMap[myId] || 0) : 0;
  if (opts.forcePop) { myScorePop = gained > 0 ? gained : myScorePop; renderScoreWithPop(score, myScorePop); return; }
  if (gained > 0) { myScorePop = gained; renderScoreWithPop(score, myScorePop); }
  else { myScorePop = 0; renderScoreWithPop(score, 0); }
}

function updateInputPlayerHeader(ranked) {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !ranked) return;
  const me = ranked.find(p => p.player_id === myId);
  if (!me) return;
  if (inputPlayerName)  inputPlayerName.textContent  = me.name  || "—";
  if (inputPlayerScore) inputPlayerScore.textContent = me.score ?? "—";
}

/* ---------- Category Input UI ---------- */
function lockCategoryInput(selectedEl) {
  categoryLocked = true;
  categorySubmitted = true;
  if (categoryInput)  { categoryInput.disabled = true;  categoryInput.classList.add("is-locked"); }
  if (categorySubmit) { categorySubmit.disabled = true; categorySubmit.classList.add("is-locked"); }

  if (suggestionBtns) {
    suggestionBtns.querySelectorAll('.yc-ctrl__sugBtn').forEach(b => b.classList.add('is-locked'));
  }

  // Gewähltes Element grün hervorheben
  if (selectedEl) selectedEl.classList.add('is-selected');
}

function renderSuggestionButtons(options) {
  if (!suggestionBtns) return;
  suggestionBtns.innerHTML = '';
  (options || []).forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'yc-ctrl__sugBtn';
    btn.textContent = opt.category;
    btn.addEventListener('pointerup', () => {
      if (categoryLocked || categorySubmitted) return;
      submitQuestionChoice(opt.id, btn);
    });
    suggestionBtns.appendChild(btn);
  });
}

function submitQuestionChoice(questionId, btn) {
  if (categoryLocked || categorySubmitted) return;
  if (!questionId) return;
  lockCategoryInput(btn);
  socket.emit("module_event", {
    action:  "submit_category",
    payload: { question_id: questionId },
  });
}

/* ---------- Category Input Event ---------- */
socket.on('yc_category_input', data => {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  currentOptions = (myId && data.player_options && data.player_options[myId]) || [];
  showScreen(ycInputScreen);
  updateInputPlayerHeader(data.players_ranked);
  renderSuggestionButtons(currentOptions);

  // Reset state
  categoryLocked = false;
  categorySubmitted = false;
  if (categoryInput)  { categoryInput.disabled = false; categoryInput.value = ''; categoryInput.classList.remove('is-locked'); }
  if (categorySubmit) { categorySubmit.disabled = false; categorySubmit.classList.remove('is-locked'); }
  if (categoryForm)   { categoryForm.style.display = ''; }
  if (categoryHint) categoryHint.classList.add('is-hidden');

  // Check if already submitted (reconnect) – kein selectedEl bekannt, einfach alles sperren
  if (myId && (data.submitted || []).includes(myId)) {
    lockCategoryInput(null);
  }

  // Start timer
  startInputTimebar(data.ends_at, data.duration || 30);
});

/* ---------- Generating / Announcement → wait screen ---------- */
socket.on('yc_generating', () => {
  stopInputTimebar();
  showScreen(titleScreen);
});

socket.on('yc_announcement', data => {
  showScreen(titleScreen);
  stopTimebar();
});

/* ---------- Round video ---------- */
socket.on('play_round_video', data => {
  if (roundLabel) roundLabel.textContent = `Frage ${data.round || 1}`;
  showScreen(roundScreen);
  resetAnswerVisuals();
  hideAnswers();
  lockAll();
  stopTimebar();
  clearUnveil();
  clearScorePopInline();
  clearQuestionResult();
});

/* ---------- show_question ---------- */
socket.on("show_question", data => {
  showScreen(qaScreen);
  if (qText) qText.textContent = data.text || "";

  // Image
  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  const imgFile = (data.image || '').trim();
  if (imgFile && qImageEl && qImageWrap) {
    qImageEl.src = imgFile.startsWith('http') || imgFile.startsWith('/')
      ? imgFile : `/yourcategory/media/images/${imgFile}`;
    qImageWrap.classList.remove('is-hidden');
  }

  (data.options || []).forEach((t, i) => { if (btns[i]) btns[i].textContent = t; });

  updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  resetAnswerVisuals();
  hideAnswers();
  lockAll();
  stopTimebar();
  clearUnveil();
  clearScorePopInline();
  clearQuestionResult();

  if (data.answers_unveil_at || data.answersUnveilAt) {
    scheduleAnswersUnveilAt(data.answers_unveil_at || data.answersUnveilAt);
  }
});

socket.on("open_answers", data => {
  resetAnswerVisuals();
  clearUnveil();
  showAnswers();
  unlockAll();
  clearQuestionResult();

  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);
  const dur = Number((data && (data.total_duration ?? data.totalDuration ?? data.duration)) || 15);
  startTimebar(dur, startedAt);
});

socket.on("close_answers", () => {
  lockAll();
  stopTimebar();
});

socket.on("reveal_player_answers", () => stopTimebar());

socket.on("unveil_correct", () => { lockAll(); stopTimebar(); });

socket.on("show_resolution", data => {
  lockAll();
  stopTimebar();
  const ci   = Number(data.correct_index);
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const myAns = (data.player_answers && myId) ? data.player_answers[myId] : null;

  btns.forEach((b, i) => {
    b.classList.remove("is-selected","is-dim","is-correct","is-wrong","is-faded");
    if (i === ci) b.classList.add("is-correct");
    else if (myAns !== null && i === Number(myAns)) b.classList.add("is-wrong");
    else b.classList.add("is-faded");
  });
  applyQuestionResult(ci, data.player_answers);
});

function isPopPayload(data) {
  const phase = (data && (data.phase || data.mode || data.step) || "").toLowerCase();
  return phase === "pop" || phase === "points_pop" || phase === "reveal_points" || phase === "show_points" || !!(data && data.show_pop === true);
}

socket.on("show_scoring", data => {
  if (isPopPayload(data)) updatePlayerHeader(data.players_ranked, data.gained || {}, { forcePop: true });
  else updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
  if (data && data.correct_index !== undefined && data.player_answers)
    applyQuestionResult(Number(data.correct_index), data.player_answers);
});

socket.on("apply_scoring_update", data => {
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
});

/* ---------- MC Button Input ---------- */
btns.forEach(btn => {
  btn.addEventListener("pointerup", () => {
    if (locked) return;
    const idx = Number(btn.dataset.index);
    lockAfterAnswer(idx);
    socket.emit("module_event", {
      action:  "submit_answer",
      payload: { index: idx },
    });
  });
});

/* ---------- Category Form ---------- */
function submitTypedCategory() {
  if (categoryLocked || categorySubmitted) return;
  const cat = (categoryInput ? categoryInput.value : '').trim();
  if (!cat) {
    if (categoryHint) {
      categoryHint.classList.remove("is-hidden");
      categoryHint.setAttribute("aria-hidden", "false");
    }
    return;
  }
  lockCategoryInput(categoryInput);
  socket.emit("module_event", {
    action:  "submit_category",
    payload: { category: cat },
  });
}

if (categoryForm) {
  categoryForm.addEventListener("submit", e => {
    e.preventDefault();
    submitTypedCategory();
  });
}

if (categoryInput) {
  categoryInput.addEventListener("input", () => {
    if (categoryHint) categoryHint.classList.add("is-hidden");
  });
  categoryInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); submitTypedCategory(); }
  });
}

/* ---------- Reconnect ---------- */
document.addEventListener("DOMContentLoaded", () => {
  const pid = localStorage.getItem(LS_PLAYER_ID_KEY);
  const rid = localStorage.getItem(LS_RUN_ID_KEY);
  if (pid) socket.emit('resume_player', { player_id: pid, run_id: rid || "" });
});

/* ---------- Init ---------- */
showScreen(titleScreen);
hideAnswers();
lockAll();
stopTimebar();
stopInputTimebar();
clearScorePopInline();
clearQuestionResult();
